import asyncio
import logging
from datetime import datetime

import httpx
from fastapi import Request, WebSocket
from flickr_url_parser import parse_flickr_url
from flickr_url_parser.exceptions import NotAFlickrUrl

from curator.app.config import FLICKR_API_KEY
from curator.asyncapi import Creator, Dates, ExistingPage, GeoLocation, MediaImage
from curator.handlers.interfaces import Handler

logger = logging.getLogger(__name__)

FLICKR_API_BASE = "https://www.flickr.com/services/rest/"
FLICKR_PAGE_SIZE = 500


def parse_album_url(url: str) -> tuple[str, str]:
    """Parse Flickr album URL to extract (photoset_id, user_id)"""
    try:
        result = parse_flickr_url(url)
    except NotAFlickrUrl:
        raise ValueError(f"Invalid Flickr URL: {url}")

    if result.get("type") != "album":
        raise ValueError(f"Expected album URL, got {result.get('type')}")

    album_id = result.get("album_id")
    if not album_id:
        raise ValueError(f"Missing album_id in URL: {url}")

    user_url = result.get("user_url", "")
    # Extract user_id from user_url (format: https://www.flickr.com/photos/{user_id}/)
    user_id = user_url.split("/")[-2] if user_url else ""
    if not user_id:
        raise ValueError(f"Missing user_id in URL: {url}")

    return album_id, user_id


def from_flickr(photo: dict, album_id: str) -> MediaImage:
    """Transform Flickr API photo response to MediaImage"""
    photo_id = photo.get("id")
    if not photo_id:
        raise ValueError("Flickr photo missing 'id' field")

    taken = photo.get("datetaken")
    if not taken:
        raise ValueError(f"Flickr photo {photo_id} missing 'datetaken' field")

    dt = datetime.strptime(taken, "%Y-%m-%d %H:%M:%S")

    owner = photo.get("owner")
    if not owner:
        raise ValueError(f"Flickr photo {photo_id} missing 'owner' field")

    nsid = owner.get("nsid") or owner.get("id")
    if not nsid:
        raise ValueError(f"Flickr photo {photo_id} missing owner 'nsid' field")

    username = owner.get("username") or owner.get("realname", "Unknown")
    path_alias = owner.get("path_alias") or nsid

    creator = Creator(
        id=str(nsid),
        username=str(username),
        profile_url=f"https://www.flickr.com/people/{path_alias}/",
    )

    geo = photo.get("geo")
    if geo and geo.get("latitude") and geo.get("longitude"):
        location = GeoLocation(
            latitude=float(geo["latitude"]),
            longitude=float(geo["longitude"]),
            compass_angle=0.0,
            accuracy=int(geo["accuracy"]) if "accuracy" in geo else None,
        )
    else:
        location = GeoLocation(
            latitude=0.0,
            longitude=0.0,
            compass_angle=0.0,
        )

    tags = photo.get("tags", "").split() if photo.get("tags") else []
    tags = [t for t in tags if t]

    title = photo.get("title", "")
    date_str = dt.date().isoformat()
    if not title:
        title = f"Photo from Flickr {date_str} ({photo_id})"
    if not title.endswith((".jpg", ".JPG", ".jpeg", ".JPEG", ".png", ".PNG")):
        title = f"{title}.jpg"

    return MediaImage(
        id=str(photo_id),
        title=str(title),
        dates=Dates(taken=dt.isoformat()),
        creator=creator,
        location=location,
        url_original=str(photo.get("url_o", "")),
        thumbnail_url=str(photo.get("url_q") or photo.get("url_s", "")),
        preview_url=str(photo.get("url_l", "")),
        url=f"https://www.flickr.com/photos/{path_alias}/{photo_id}",
        width=int(
            photo.get("width_o") or photo.get("o_width") or photo.get("width_l") or 0
        ),
        height=int(
            photo.get("height_o") or photo.get("o_height") or photo.get("height_l") or 0
        ),
        license=str(photo.get("license", "")),
        tags=tags,
        existing=[],
    )


async def _fetch_album_page(page: int, photoset_id: str, user_id: str) -> dict:
    """Fetch single page of album photos"""
    logger.info(f"[flickr] fetching page {page} for album {photoset_id}")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            FLICKR_API_BASE,
            params={
                "method": "flickr.photosets.getPhotos",
                "api_key": FLICKR_API_KEY,
                "photoset_id": photoset_id,
                "user_id": user_id,
                "page": page,
                "per_page": FLICKR_PAGE_SIZE,
                "extras": "description,license,date_taken,geo,tags,url_o,url_l,url_q,url_s,original_format",
                "format": "json",
                "nojsoncallback": "1",
            },
            timeout=60,
        )
    response.raise_for_status()
    data = response.json()

    if data.get("stat") != "ok":
        raise ValueError(f"Flickr API error: {data.get('message', 'Unknown error')}")

    return data


async def _fetch_album_ids(photoset_id: str, user_id: str) -> list[str]:
    """Fetch all photo IDs from album with pagination handling"""
    first_page = await _fetch_album_page(1, photoset_id, user_id)
    photoset = first_page["photoset"]
    total_pages = int(photoset["pages"])
    all_ids = [p["id"] for p in photoset["photo"]]

    if total_pages > 1:
        tasks = [
            _fetch_album_page(page, photoset_id, user_id)
            for page in range(2, total_pages + 1)
        ]
        pages = await asyncio.gather(*tasks)

        for page_data in pages:
            all_ids.extend(p["id"] for p in page_data["photoset"]["photo"])

    return all_ids


async def _fetch_photos_by_ids(
    image_ids: list[str], photoset_id: str, user_id: str
) -> dict[str, dict]:
    """
    Fetch multiple photos by their IDs from the album.
    This iterates through album pages until all requested IDs are found.
    """
    logger.info(f"[flickr] fetching {len(image_ids)} photos from album {photoset_id}")

    ids_to_fetch = set(image_ids)
    page = 1
    all_photos = {}

    while ids_to_fetch:
        page_data = await _fetch_album_page(page, photoset_id, user_id)
        photos = page_data["photoset"]["photo"]

        for photo in photos:
            if photo["id"] in ids_to_fetch:
                all_photos[photo["id"]] = photo
                ids_to_fetch.remove(photo["id"])

        if not ids_to_fetch:
            break

        # Check if we've reached the last page
        if page >= int(page_data["photoset"]["pages"]):
            break

        page += 1

    return all_photos


async def fetch_photos_batch(
    image_ids: list[str], photoset_id: str, user_id: str
) -> dict[str, dict]:
    """Fetch batch of photos from album"""
    if not image_ids:
        return {}

    return await _fetch_photos_by_ids(image_ids, photoset_id, user_id)


async def _fetch_photo_details(photo_id: str) -> dict:
    """Fetch single photo details using flickr.photos.getInfo"""
    logger.info(f"[flickr] fetching details for photo {photo_id}")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            FLICKR_API_BASE,
            params={
                "method": "flickr.photos.getInfo",
                "api_key": FLICKR_API_KEY,
                "photo_id": photo_id,
                "format": "json",
                "nojsoncallback": "1",
            },
            timeout=60,
        )
    response.raise_for_status()
    data = response.json()

    if data.get("stat") != "ok":
        raise ValueError(f"Flickr API error: {data.get('message', 'Unknown error')}")

    return data["photo"]


class FlickrHandler(Handler):
    name = "flickr"

    async def fetch_collection(self, input: str) -> dict[str, MediaImage]:
        """Fetch all images from Flickr album"""
        photoset_id, user_id = parse_album_url(input)

        image_ids = await _fetch_album_ids(photoset_id, user_id)

        all_images = {}
        for i in range(0, len(image_ids), FLICKR_PAGE_SIZE):
            batch_ids = image_ids[i : i + FLICKR_PAGE_SIZE]
            batch_data = await fetch_photos_batch(batch_ids, photoset_id, user_id)
            all_images.update(batch_data)

        return {k: from_flickr(v, photoset_id) for k, v in all_images.items()}

    async def fetch_collection_ids(self, input: str) -> list[str]:
        """Fetch only photo IDs from album"""
        photoset_id, user_id = parse_album_url(input)
        return await _fetch_album_ids(photoset_id, user_id)

    async def fetch_images_batch(
        self, image_ids: list[str], collection: str
    ) -> dict[str, MediaImage]:
        """Fetch batch of images by IDs from the collection"""
        photoset_id, user_id = parse_album_url(collection)
        data = await fetch_photos_batch(image_ids, photoset_id, user_id)
        return {k: from_flickr(v, photoset_id) for k, v in data.items()}

    async def fetch_image_metadata(
        self, image_id: str, input: str | None = None
    ) -> MediaImage:
        """Fetch single image metadata"""
        photo_data = await _fetch_photo_details(image_id)
        return from_flickr(photo_data, "")

    def fetch_existing_pages(
        self, image_ids: list[str], request: Request | WebSocket
    ) -> dict[str, list[ExistingPage]]:
        """
        Query WCQS for existing Flickr photo uploads

        TODO: Determine correct Wikidata property for Flickr photo IDs
        """
        return {}

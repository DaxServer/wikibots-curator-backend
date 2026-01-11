import logging
from datetime import datetime
from typing import Any, Optional, Union

import httpx
from fastapi import Request, WebSocket

from curator.app.config import (
    MAPILLARY_API_TOKEN,
    WikidataProperty,
)
from curator.app.wcqs import WcqsSession
from curator.asyncapi import Creator, Dates, ExistingPage, GeoLocation, MediaImage
from curator.handlers.interfaces import Handler

logger = logging.getLogger(__name__)


def from_mapillary(image: dict[str, Any]) -> MediaImage:
    geometry = image.get("geometry")
    if not geometry:
        raise ValueError(f"Image {image.get('id')} has no geometry")
    coords = geometry.get("coordinates")
    if not coords or len(coords) < 2:
        raise ValueError(f"Image {image.get('id')} has invalid coordinates")

    owner = image.get("creator")
    if not owner:
        raise ValueError(f"Image {image.get('id')} has no creator")

    creator = Creator(
        id=str(owner.get("id")),
        username=str(owner.get("username", "Unknown")),
        profile_url=f"https://www.mapillary.com/app/user/{owner.get('username', 'unknown')}",
    )
    loc = GeoLocation(
        latitude=float(coords[1]),
        longitude=float(coords[0]),
        compass_angle=float(image.get("compass_angle", 0.0)),
    )
    captured_at = image.get("captured_at")
    if captured_at is None:
        raise ValueError(f"Image {image.get('id')} has no captured_at")

    dt = datetime.fromtimestamp(captured_at / 1000.0)
    date = dt.date().isoformat()
    return MediaImage(
        id=str(image.get("id")),
        title=f"Photo from Mapillary {date} ({str(image.get('id'))}).jpg",
        dates=Dates(taken=dt.isoformat()),
        creator=creator,
        location=loc,
        url_original=str(image.get("thumb_original_url", "")),
        url=f"https://www.mapillary.com/app/?pKey={image.get('id')}&focus=photo",
        thumbnail_url=str(image.get("thumb_256_url", "")),
        preview_url=str(image.get("thumb_1024_url", "")),
        width=int(image.get("width", 0)),
        height=int(image.get("height", 0)),
        camera_make=image.get("make"),
        camera_model=image.get("model"),
        is_pano=image.get("is_pano"),
        existing=[],
    )


async def _fetch_sequence_data(sequence_id: str) -> dict:
    """
    Fetch sequence data from Mapillary API
    """
    logger.info(f"[mapillary] fetching sequence data for {sequence_id}")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://graph.mapillary.com/images",
            params={
                "access_token": MAPILLARY_API_TOKEN,
                "sequence_ids": sequence_id,
                "fields": "captured_at,compass_angle,creator,geometry,height,is_pano,make,model,thumb_256_url,thumb_1024_url,thumb_original_url,width",
            },
            timeout=60,
        )
    response.raise_for_status()
    images = response.json()["data"]

    # sort by captured_at
    images.sort(key=lambda x: x["captured_at"])

    return {str(i["id"]): i for i in images}


async def _get_sequence_ids(sequence_id: str) -> list[str]:
    """
    Fetch sequence image IDs from Mapillary API (no fields)
    """
    logger.info(f"[mapillary] fetching sequence ids for {sequence_id}")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://graph.mapillary.com/images",
            params={
                "access_token": MAPILLARY_API_TOKEN,
                "sequence_ids": sequence_id,
            },
            timeout=60,
        )
    response.raise_for_status()
    images = response.json()["data"]
    return [str(i["id"]) for i in images]


async def _fetch_images_by_ids_api(image_ids: list[str]) -> dict[str, dict]:
    """
    Fetch multiple images by their IDs in a single request.
    """
    if not image_ids:
        return {}

    logger.info(f"[mapillary] fetching {len(image_ids)} images by ids")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://graph.mapillary.com",
            params={
                "access_token": MAPILLARY_API_TOKEN,
                "ids": ",".join(image_ids),
                "fields": "captured_at,compass_angle,creator,geometry,height,is_pano,make,model,thumb_256_url,thumb_1024_url,thumb_original_url,width",
            },
            timeout=60,
        )
    response.raise_for_status()
    return {str(k): v for k, v in response.json().items()}


async def _fetch_single_image(image_id: str) -> dict:
    """
    Fetch single image data from Mapillary API
    """
    logger.info(f"[mapillary] fetching single image data for {image_id}")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://graph.mapillary.com/{image_id}",
            params={
                "access_token": MAPILLARY_API_TOKEN,
                "fields": "captured_at,compass_angle,creator,geometry,height,is_pano,make,model,thumb_256_url,thumb_1024_url,thumb_original_url,width",
            },
            timeout=60,
        )
    response.raise_for_status()
    return response.json()


class MapillaryHandler(Handler):
    @property
    def name(self) -> str:
        return "mapillary"

    async def fetch_collection(self, input: str) -> dict[str, MediaImage]:
        collection = await _fetch_sequence_data(input)
        return {k: from_mapillary(v) for k, v in collection.items()}

    async def fetch_collection_ids(self, input: str) -> list[str]:
        return await _get_sequence_ids(input)

    async def fetch_images_batch(
        self, image_ids: list[str], input: str
    ) -> dict[str, MediaImage]:
        data = await _fetch_images_by_ids_api(image_ids)
        return {k: from_mapillary(v) for k, v in data.items()}

    async def fetch_image_metadata(
        self, image_id: str, input: Optional[str] = None
    ) -> MediaImage:
        image = await _fetch_single_image(image_id)

        if not image:
            raise ValueError(f"Image data not found for image_id={image_id}")

        return from_mapillary(image)

    def fetch_existing_pages(
        self, image_ids: list[str], request: Union[Request, WebSocket]
    ) -> dict[str, list[ExistingPage]]:
        """
        Fetch existing Wikimedia Commons pages for the given Mapillary image IDs.

        Queries WCQS to find files that have already been uploaded with these Mapillary IDs
        to prevent duplicate uploads.
        """
        query = f"""
            SELECT ?file ?id WHERE {{
              VALUES ?id {{ {" ".join([f'"{i}"' for i in image_ids])} }}
              ?file wdt:{WikidataProperty.MapillaryPhotoID} ?id.
            }}
            """

        results = WcqsSession(request).query(query)

        existing_pages = {}
        for r in results["results"]["bindings"]:
            image_id = r["id"]["value"]
            file_url = r["file"]["value"]
            if image_id not in existing_pages:
                existing_pages[image_id] = []
            existing_pages[image_id].append(ExistingPage(url=file_url))

        return existing_pages

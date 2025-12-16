import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Union

import httpx
from fastapi import Request, WebSocket

from curator.app.config import (
    MAPILLARY_API_TOKEN,
    WikidataProperty,
    cache,
)
from curator.app.ingest.interfaces import Handler
from curator.app.wcqs import WcqsSession
from curator.asyncapi import Creator, Dates, ExistingPage, Image, Location

logger = logging.getLogger(__name__)


def from_mapillary(image: Dict[str, Any]) -> Image:
    coords = image.get("geometry").get("coordinates")
    owner = image.get("creator")
    creator = Creator(
        id=str(owner.get("id")),
        username=owner.get("username"),
        profile_url=f"https://www.mapillary.com/app/user/{owner.get('username')}",
    )
    loc = Location(
        latitude=coords[1],
        longitude=coords[0],
        compass_angle=image.get("compass_angle"),
    )
    dt = datetime.fromtimestamp(image.get("captured_at") / 1000.0)
    date = dt.date().isoformat()
    return Image(
        id=str(image.get("id")),
        title=f"Photo from Mapillary {date} ({str(image.get('id'))}).jpg",
        dates=Dates(taken=dt.isoformat()),
        creator=creator,
        location=loc,
        url_original=image.get("thumb_original_url"),
        url=f"https://www.mapillary.com/app/?pKey={image.get('id')}&focus=photo",
        thumbnail_url=image.get("thumb_256_url"),
        preview_url=image.get("thumb_1024_url"),
        width=image.get("width"),
        height=image.get("height"),
        camera_make=image.get("make"),
        camera_model=image.get("model"),
        is_pano=image.get("is_pano"),
        existing=[],
        tags=[],
        description="",
    )


@cache(ttl=timedelta(hours=1), key="curator:mapillary:sequence:{sequence_id}")
async def _fetch_sequence_data(sequence_id: str) -> dict:
    """
    Fetch sequence data from Mapillary API
    """
    logger.info(f"[mapillary] fetching sequence data for {sequence_id}")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://graph.mapillary.com/images",
            params={
                "access_token": MAPILLARY_API_TOKEN,
                "sequence_ids": sequence_id,
                "fields": "captured_at,compass_angle,creator,geometry,height,is_pano,make,model,thumb_256_url,thumb_1024_url,thumb_original_url,width",
            },
            timeout=30,
        )
    response.raise_for_status()
    images = response.json()["data"]

    # sort by captured_at
    images.sort(key=lambda x: x["captured_at"])

    return {str(i["id"]): i for i in images}


@cache(ttl=timedelta(hours=1), key="curator:mapillary:image:{image_id}")
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
            timeout=30,
        )
    response.raise_for_status()
    return response.json()


class MapillaryHandler(Handler):
    name = "mapillary"

    async def fetch_collection(self, input: str) -> Dict[str, Image]:
        collection = await _fetch_sequence_data(input)
        return {k: from_mapillary(v) for k, v in collection.items()}

    async def fetch_image_metadata(
        self, image_id: str, collection_id: str | None = None
    ) -> Image:
        if collection_id:
            collection = await _fetch_sequence_data(collection_id)
            image = collection.get(image_id)
        else:
            # Fallback for legacy uploads where collection/sequence ID is missing
            image = await _fetch_single_image(image_id)

        if not image:
            context = "sequence" if collection_id else "Mapillary API"
            raise ValueError(
                f"Image data not found in {context} for image_id={image_id}"
            )

        return from_mapillary(image)

    def fetch_existing_pages(
        self, image_ids: List[str], request: Union[Request, WebSocket]
    ) -> Dict[str, List[ExistingPage]]:
        """
        Fetch existing Wikimedia Commons pages for the given Mapillary image IDs.

        Queries WCQS to find files that have already been uploaded with these Mapillary IDs
        to prevent duplicate uploads.
        """
        query = f"""
            SELECT ?file ?id WHERE {{
              VALUES ?id {{ { " ".join([f'"{i}"' for i in image_ids]) } }}
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

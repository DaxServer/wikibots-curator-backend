from datetime import timedelta
import logging
from curator.app.config import cache
from curator.app.wcqs import WcqsSession
from pywikibot import WbQuantity
from datetime import datetime
from typing import Any, Dict, List, Union
from fastapi import Request, WebSocket

from curator.app.config import (
    MAPILLARY_API_TOKEN,
    PWB_SITE_COMMONS,
    PWB_SITE_WIKIDATA,
    WikidataEntity,
    WikidataProperty,
)
from curator.app.image_models import Creator, Image, Location, Dates, ExistingPage
from curator.app.ingest.interfaces import Handler
import httpx
from pywikibot import Claim, ItemPage, Timestamp, WbTime

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
        dates=Dates(taken=dt),
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


class MapillaryHandler(Handler):
    name = "mapillary"

    async def fetch_collection(self, input: str) -> Dict[str, Image]:
        collection = await _fetch_sequence_data(input)
        return {k: from_mapillary(v) for k, v in collection.items()}

    async def fetch_image_metadata(self, image_id: str, input: str) -> Image:
        collection = await _fetch_sequence_data(input)
        image = collection.get(image_id)
        if not image:
            raise ValueError(
                f"Image data not found in sequence for image_id={image_id}"
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

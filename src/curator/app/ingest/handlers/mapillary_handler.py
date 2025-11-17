from functools import lru_cache
from typing import Dict, List

from curator.app.config import MAPILLARY_API_TOKEN
from curator.app.sdc import build_mapillary_sdc
from curator.app.image_models import Image, from_mapillary
from curator.app.ingest.interfaces import Handler
import httpx


@lru_cache(maxsize=128)
def _fetch_sequence_data(sequence_id: str) -> dict:
    """
    Fetch sequence data from Mapillary API
    """
    response = httpx.get(
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

    def fetch_collection(self, input: str) -> Dict[str, Image]:
        source = _fetch_sequence_data(input)
        return {k: from_mapillary(v) for k, v in source.items()}

    def fetch_image_metadata(self, image_id: str, input: str) -> Image:
        collection = self.fetch_collection(input)
        image = collection.get(image_id)
        if not image:
            raise ValueError(
                f"Image data not found in sequence for image_id={image_id}"
            )
        return image

    def build_sdc(self, image: Image) -> List[Dict]:
        return build_mapillary_sdc(image)

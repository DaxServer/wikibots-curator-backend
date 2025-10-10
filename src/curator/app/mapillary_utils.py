from functools import lru_cache
import httpx
from curator.app.config import MAPILLARY_API_TOKEN


@lru_cache(maxsize=128)
def fetch_sequence_data(sequence_id: str) -> dict:
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

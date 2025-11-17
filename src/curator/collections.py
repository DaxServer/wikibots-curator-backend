from typing import List, Dict, Literal
from fastapi import APIRouter
from pydantic import BaseModel

from curator.app.ingest.handlers.mapillary_handler import MapillaryHandler


router = APIRouter(prefix="/api/collections", tags=["collections"])


class ImagesRequest(BaseModel):
    handler: Literal["mapillary"]
    input: str


class SdcRequest(ImagesRequest):
    images: List[str] = []


@router.post("/images")
async def post_collection_images(payload: ImagesRequest):
    handler = MapillaryHandler()
    images = handler.fetch_collection(payload.input)

    first = next(iter(images.values()))
    creator = first.creator.model_dump()

    return {"images": images, "creator": creator}


@router.post("/sdc")
async def post_collection_sdc(payload: SdcRequest):
    expanded: List[str] = []
    for v in payload.images:
        expanded.extend([x for x in v.split(",") if x])

    handler = MapillaryHandler()
    collection = handler.fetch_collection(payload.input)

    result: Dict[str, Dict] = {}
    for image_id in expanded:
        image = collection.get(image_id)
        if image:
            result[image_id] = handler.build_sdc(image)

    return result

from typing import List, Dict, Literal
from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel

from curator.app.ingest.handlers.mapillary_handler import MapillaryHandler


router = APIRouter(prefix="/api/collections", tags=["collections"])


class ImagesRequest(BaseModel):
    handler: Literal["mapillary"]
    input: str


class SdcRequest(ImagesRequest):
    images: List[str] = []


@router.post("/images")
async def post_collection_images(request: Request, payload: ImagesRequest):
    handler = MapillaryHandler()
    images = handler.fetch_collection(payload.input)

    if not images:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found"
        )

    first = next(iter(images.values()))
    creator = first.creator.model_dump()

    existing_pages = handler.fetch_existing_pages(
        [i.id for i in images.values()], request
    )
    for image_id, pages in existing_pages.items():
        images[image_id].existing = pages

    return {"images": images, "creator": creator}


@router.post("/sdc")
async def post_collection_sdc(payload: SdcRequest):
    expanded: List[str] = []
    for v in payload.images:
        expanded.extend([x for x in v.split(",") if x])

    handler = MapillaryHandler()
    images = handler.fetch_collection(payload.input)

    result: Dict[str, Dict] = {}
    for image_id in expanded:
        if image_id in images:
            result[image_id] = handler.build_sdc(images[image_id])

    return result

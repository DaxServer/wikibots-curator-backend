from curator.app.auth import check_login
from typing import List, Literal
from fastapi import APIRouter, Depends, Request, HTTPException, status
from pydantic import BaseModel

from curator.app.ingest.handlers.mapillary_handler import MapillaryHandler


router = APIRouter(
    prefix="/api/collections", tags=["collections"], dependencies=[Depends(check_login)]
)


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

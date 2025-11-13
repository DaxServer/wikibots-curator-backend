from curator.app.config import MAPILLARY_API_TOKEN
from curator.workers.mapillary import process_one
from typing import List
from fastapi import (
    APIRouter,
    Depends,
    Request,
    HTTPException,
    status,
    Query,
    BackgroundTasks,
)
import httpx
from sqlalchemy.orm import Session
from curator.app.db import get_session
from curator.app.dal import (
    create_upload_request,
    get_upload_request,
)
from mwoauth import AccessToken

from curator.app.models import UploadItem
from curator.app.sdc import build_mapillary_sdc
from curator.app.mapillary_utils import fetch_sequence_data


router = APIRouter(prefix="/api/mapillary", tags=["mapillary"])


@router.get("/images/{image_id}")
async def get_image(image_id: str):
    """
    Fetches a single image from Mapillary API.
    """

    with httpx.Client() as client:
        response = client.get(
            f"https://graph.mapillary.com/{image_id}",
            params={
                "access_token": MAPILLARY_API_TOKEN,
                # "fields": "thumb_original_url",
                "fields": "captured_at,compass_angle,creator,geometry,height,is_pano,make,model,thumb_256_url,thumb_1024_url,thumb_original_url,width",
            },
            timeout=30,
        )
        response.raise_for_status()

        return response.json()


@router.get("/sequences/{sequence_id}")
async def get_images_in_sequence(sequence_id: str):
    """
    Fetches images in a given sequence from Mapillary API.
    Uses cached data to avoid repeated API calls.
    """
    images = fetch_sequence_data(sequence_id)

    # with open(os.path.join(os.path.dirname(__file__), "../../images.json"), "rb") as f:
    #     return json.load(f)

    return {
        "creator": next(iter(images.values())).get("creator", {}),
        "images": {
            k: {k2: v2 for k2, v2 in v.items() if k2 != "creator"}
            for k, v in images.items()
        },
    }


@router.get("/sequences/{sequence_id}/sdc")
async def get_sequence_sdc(
    sequence_id: str,
    images: List[str] = Query([], description="List of image IDs to get SDC for"),
):
    """
    Fetches SDC (Structured Data on Commons) for specific images in a sequence.
    Returns a JSON object with image IDs as keys and their SDC data as values.
    """
    expanded: List[str] = []
    for v in images:
        expanded.extend([x for x in v.split(",") if x])
    result = {}
    for image in fetch_sequence_data(sequence_id).values():
        image_id = image["id"]
        if image_id in expanded:
            sdc_data = build_mapillary_sdc(image)
            result[image_id] = sdc_data

    return result


@router.post("/upload")
def ingest_upload(
    request: Request,
    payload: list[UploadItem],
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    username: str | None = request.session.get("user", {}).get("username")
    userid: str | None = request.session.get("user", {}).get("sub")
    access_token: AccessToken | None = request.session.get("access_token")

    if not username or not userid or not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )

    sequence_id = payload[0].sequence_id

    reqs = create_upload_request(
        session=session,
        username=username,
        userid=userid,
        payload=payload,
    )

    # Ensure IDs are materialized and persisted before enqueuing tasks
    session.commit()

    for req in reqs:
        background_tasks.add_task(
            process_one.delay, req.id, sequence_id, access_token, username
        )

    return [
        {
            "id": r.id,
            "status": r.status,
            "image_id": r.key,
            "sequence_id": sequence_id,
            "batch_id": r.batch_id,
        }
        for r in reqs
    ]


@router.get("/uploads/{batch_id}")
async def get_uploads_by_batch(
    request: Request,
    batch_id: str,
    session: Session = Depends(get_session),
):
    username: str | None = request.session.get("user", {}).get("username")
    userid: str | None = request.session.get("user", {}).get("sub")
    if not username or not userid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )

    items = get_upload_request(session, userid=userid, batch_id=batch_id)

    return [
        {
            "id": r.id,
            "status": r.status,
            "image_id": r.key,
            "batch_id": r.batch_id,
            "result": r.result,
            "error": r.error,
        }
        for r in items
    ]

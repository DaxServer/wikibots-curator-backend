from typing import Literal

from fastapi import APIRouter, Depends, Request, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from mwoauth import AccessToken

from curator.app.db import get_session
from curator.app.dal import (
    create_upload_request,
    get_upload_request,
    get_batches,
    count_batches,
    count_uploads_in_batch,
)
from curator.app.crypto import encrypt_access_token
from curator.app.models import UploadItem
from pydantic import BaseModel
from curator.workers.ingest import process_one as ingest_process_one


router = APIRouter(prefix="/api/ingest", tags=["ingest"])


class UploadItemsPayload(BaseModel):
    handler: Literal["mapillary"]
    items: list[UploadItem]


@router.post("/upload")
def ingest_upload(
    request: Request,
    payload: UploadItemsPayload,
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

    raw_input = payload.items[0].input
    handler = payload.handler

    reqs = create_upload_request(
        session=session,
        username=username,
        userid=userid,
        payload=payload.items,
        handler=handler,
    )

    session.commit()

    for req in reqs:
        background_tasks.add_task(
            ingest_process_one.delay,
            req.id,
            raw_input,
            encrypt_access_token(access_token),
            username,
        )

    return [
        {
            "id": r.id,
            "status": r.status,
            "image_id": r.key,
            "input": raw_input,
            "batch_id": r.batchid,
        }
        for r in reqs
    ]


@router.get("/batches")
async def get_user_batches(
    request: Request,
    page: int = 1,
    limit: int = 100,
    session: Session = Depends(get_session),
):
    userid: str | None = request.session.get("user", {}).get("sub")
    if not userid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )

    offset = (page - 1) * limit
    batches = get_batches(session, userid=userid, offset=offset, limit=limit)
    total = count_batches(session, userid=userid)

    return {
        "items": [
            {
                "batch_id": b.id,
                "created_at": b.created_at,
                "uploads": [
                    {
                        "id": r.id,
                        "status": r.status,
                        "image_id": r.key,
                        "batch_id": r.batchid,
                        "result": r.result,
                        "error": r.error,
                        "success": r.success,
                        "handler": r.handler,
                    }
                    for r in b.uploads
                ],
            }
            for b in batches
        ],
        "total": total,
    }


@router.get("/uploads/{batch_id}")
async def get_uploads_by_batch(
    request: Request,
    batch_id: int,
    page: int = 1,
    limit: int = 100,
    session: Session = Depends(get_session),
):
    userid: str | None = request.session.get("user", {}).get("sub")
    if not userid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )

    offset = (page - 1) * limit
    items = get_upload_request(
        session, userid=userid, batch_id=batch_id, offset=offset, limit=limit
    )
    total = count_uploads_in_batch(session, userid=userid, batch_id=batch_id)

    return {
        "items": [
            {
                "id": r.id,
                "status": r.status,
                "image_id": r.key,
                "batch_id": r.batchid,
                "result": r.result,
                "error": r.error,
                "success": r.success,
                "handler": r.handler,
            }
            for r in items
        ],
        "total": total,
    }

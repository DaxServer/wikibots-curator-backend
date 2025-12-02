from curator.app.auth import check_login
from curator.app.auth import LoggedInUser
from typing import Literal, Optional

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from curator.app.db import get_session
from curator.app.dal import (
    create_upload_request,
    get_upload_request,
    get_batches as dal_get_batches,
    count_batches,
    count_uploads_in_batch,
)
from curator.app.crypto import encrypt_access_token
from curator.app.models import UploadItem
from pydantic import BaseModel
from curator.workers.ingest import process_one as ingest_process_one


router = APIRouter(
    prefix="/api/ingest", tags=["ingest"], dependencies=[Depends(check_login)]
)


class UploadItemsPayload(BaseModel):
    handler: Literal["mapillary"]
    items: list[UploadItem]


@router.post("/upload")
async def ingest_upload(
    payload: UploadItemsPayload,
    background_tasks: BackgroundTasks,
    user: LoggedInUser,
    session: Session = Depends(get_session),
):
    raw_input = payload.items[0].input
    handler = payload.handler

    reqs = create_upload_request(
        session=session,
        username=user["username"],
        userid=user["userid"],
        payload=payload.items,
        handler=handler,
    )

    session.commit()

    for req in reqs:
        background_tasks.add_task(
            ingest_process_one.delay,
            req.id,
            raw_input,
            encrypt_access_token(user["access_token"]),
            user["username"],
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
async def get_batches(
    userid: Optional[str] = None,
    page: int = 1,
    limit: int = 100,
    session: Session = Depends(get_session),
):
    offset = (page - 1) * limit
    batches = dal_get_batches(session, userid=userid, offset=offset, limit=limit)
    total = count_batches(session, userid=userid)

    return {
        "items": [
            {
                "id": b.id,
                "created_at": b.created_at,
                "username": b.user.username,
                "userid": b.user.userid,
                "uploads": [
                    {
                        "id": r.id,
                        "status": r.status,
                        "image_id": r.key,
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
    batch_id: int,
    page: int = 1,
    limit: int = 100,
    columns: Optional[str] = None,
    session: Session = Depends(get_session),
):
    offset = (page - 1) * limit
    column_list = (
        columns.split(",")
        if columns
        else ["id", "status", "key", "batchid", "error", "success", "handler"]
    )

    items = get_upload_request(
        session, batch_id=batch_id, offset=offset, limit=limit, columns=column_list
    )
    total = count_uploads_in_batch(session, batch_id=batch_id)

    return {
        "items": [
            {col: getattr(r, col) for col in column_list if hasattr(r, col)}
            for r in items
        ],
        "total": total,
    }

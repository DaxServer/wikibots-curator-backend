from typing import Literal
import json

from fastapi import APIRouter, Depends, Request, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from mwoauth import AccessToken

from curator.app.db import get_session
from curator.app.dal import create_upload_request, get_upload_request
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
            "error": (json.loads(r.error) if r.error else None),
            "success": r.success,
            "handler": r.handler,
        }
        for r in items
    ]

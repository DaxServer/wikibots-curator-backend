from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session

from curator.app.auth import LoggedInUser
from curator.app.crypto import encrypt_access_token
from curator.app.dal import (
    count_all_upload_requests,
    count_batches,
    count_users,
    get_all_upload_requests,
    get_batches,
    get_users,
    retry_batch_as_admin,
)
from curator.app.db import engine
from curator.app.models import UploadRequest
from curator.workers.tasks import process_upload


def check_admin(request: Request):
    username = request.session.get("user", {}).get("username")
    if username != "DaxServer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(check_admin)]
)


@router.get("/batches")
async def admin_get_batches(
    page: int = 1,
    limit: int = 100,
):
    offset = (page - 1) * limit
    with Session(engine) as session:
        items = get_batches(session, offset=offset, limit=limit)
        total = count_batches(session)
    return {"items": items, "total": total}


@router.get("/users")
async def admin_get_users(
    page: int = 1,
    limit: int = 100,
):
    offset = (page - 1) * limit
    with Session(engine) as session:
        items = get_users(session, offset=offset, limit=limit)
        total = count_users(session)
    return {"items": items, "total": total}


@router.get("/upload_requests")
async def admin_get_upload_requests(
    page: int = 1,
    limit: int = 100,
):
    offset = (page - 1) * limit
    with Session(engine) as session:
        items = get_all_upload_requests(session, offset=offset, limit=limit)
        total = count_all_upload_requests(session)
    return {"items": items, "total": total}


@router.put("/upload_requests/{upload_request_id}")
async def admin_update_upload_request(
    upload_request_id: int,
    update_data: dict,
):
    with Session(engine) as session:
        upload_request = session.get(UploadRequest, upload_request_id)
        if not upload_request:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        for key, value in update_data.items():
            setattr(upload_request, key, value)

        session.commit()
    return {"message": "Upload request updated successfully"}


@router.post("/batches/{batch_id}/retry")
async def admin_retry_batch(
    batch_id: int,
    user: LoggedInUser,
):
    with Session(engine) as session:
        # Encrypt the admin's token
        encrypted_token = encrypt_access_token(user["access_token"])

        try:
            reset_ids = retry_batch_as_admin(
                session, batch_id, encrypted_token, user["userid"]
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    # Queue the uploads for processing
    for upload_id in reset_ids:
        process_upload.delay(upload_id)

    return {"message": f"Retried {len(reset_ids)} uploads"}

from fastapi import APIRouter, Depends, HTTPException, Request, status

from curator.app.auth import LoggedInUser
from curator.app.crypto import encrypt_access_token
from curator.app.dal import (
    count_all_upload_requests,
    count_batches,
    count_users,
    get_all_upload_requests,
    get_batches,
    get_users,
    retry_selected_uploads_to_new_batch,
    update_celery_task_id,
)
from curator.app.db import get_session
from curator.app.models import RetrySelectedUploadsRequest, UploadRequest
from curator.workers.celery import QUEUE_PRIVILEGED
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
    with get_session() as session:
        items = get_batches(session, offset=offset, limit=limit)
        total = count_batches(session)
    return {"items": items, "total": total}


@router.get("/users")
async def admin_get_users(
    page: int = 1,
    limit: int = 100,
):
    offset = (page - 1) * limit
    with get_session() as session:
        items = get_users(session, offset=offset, limit=limit)
        total = count_users(session)
        # Serialize User objects to dicts BEFORE session closes
        serialized = [u.model_dump() for u in items]
    return {"items": serialized, "total": total}


@router.get("/upload_requests")
async def admin_get_upload_requests(
    page: int = 1,
    limit: int = 100,
):
    offset = (page - 1) * limit
    with get_session() as session:
        items = get_all_upload_requests(session, offset=offset, limit=limit)
        total = count_all_upload_requests(session)
    return {"items": items, "total": total}


@router.put("/upload_requests/{upload_request_id}")
async def admin_update_upload_request(
    upload_request_id: int,
    update_data: dict,
):
    with get_session() as session:
        upload_request = session.get(UploadRequest, upload_request_id)
        if not upload_request:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        for key, value in update_data.items():
            setattr(upload_request, key, value)
    return {"message": "Upload request updated successfully"}


@router.post("/retry")
async def admin_retry_uploads(
    request: RetrySelectedUploadsRequest,
    user: LoggedInUser,
):
    with get_session() as session:
        encrypted_token = encrypt_access_token(user["access_token"])

        reset_ids, edit_group_id, new_batch_id = retry_selected_uploads_to_new_batch(
            session,
            request.upload_ids,
            encrypted_token,
            user["userid"],
            user["username"],
        )

    # Queue the uploads for processing with new batch's edit_group_id (admin retries always use privileged queue)

    if not reset_ids or not edit_group_id:
        return {
            "message": "Retried 0 uploads",
            "retried_count": 0,
            "requested_count": len(request.upload_ids),
            "new_batch_id": None,
        }

    tasks_to_update = []
    for upload_id in reset_ids:
        task_result = process_upload.apply_async(
            args=[upload_id, edit_group_id], queue=QUEUE_PRIVILEGED
        )
        task_id = task_result.id
        if isinstance(task_id, str):
            tasks_to_update.append((upload_id, task_id))

    if tasks_to_update:
        with get_session() as session:
            for upload_id, task_id in tasks_to_update:
                update_celery_task_id(session, upload_id, task_id)

    return {
        "message": f"Retried {len(reset_ids)} uploads",
        "retried_count": len(reset_ids),
        "requested_count": len(request.upload_ids),
        "new_batch_id": new_batch_id,
    }

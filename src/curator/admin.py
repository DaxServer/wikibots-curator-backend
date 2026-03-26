from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from curator.app.auth import LoggedInUser
from curator.app.crypto import encrypt_access_token
from curator.app.dal import (
    cancel_upload_requests,
    count_all_presets,
    count_all_upload_requests,
    count_batches,
    count_users,
    fail_upload_requests,
    get_all_presets,
    get_all_upload_requests,
    get_batches,
    get_failed_uploads_grouped,
    get_users,
    retry_selected_uploads_to_new_batch,
    update_celery_task_id,
)
from curator.app.db import get_session
from curator.app.models import (
    BulkCancelRequest,
    BulkFailRequest,
    RetrySelectedUploadsRequest,
    UploadRequest,
)
from curator.workers.celery import QUEUE_NORMAL
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
    filter_text: str | None = None,
):
    offset = (page - 1) * limit
    with get_session() as session:
        items = get_batches(
            session, offset=offset, limit=limit, filter_text=filter_text
        )
        total = count_batches(session, filter_text=filter_text)
    return {"items": items, "total": total}


@router.get("/users")
async def admin_get_users(
    page: int = 1,
    limit: int = 100,
    filter_text: str | None = None,
):
    offset = (page - 1) * limit
    with get_session() as session:
        items = get_users(session, offset=offset, limit=limit, filter_text=filter_text)
        total = count_users(session, filter_text=filter_text)
        # Serialize User objects to dicts BEFORE session closes
        serialized = [u.model_dump() for u in items]
    return {"items": serialized, "total": total}


@router.get("/upload_requests")
async def admin_get_upload_requests(
    page: int = 1,
    limit: int = 100,
    filter_text: str | None = None,
    status: list[str] | None = Query(default=None),
    date_from: date | None = None,
    date_to: date | None = None,
):
    offset = (page - 1) * limit
    with get_session() as session:
        items = get_all_upload_requests(
            session,
            offset=offset,
            limit=limit,
            filter_text=filter_text,
            statuses=status,
            date_from=date_from,
            date_to=date_to,
        )
        total = count_all_upload_requests(
            session,
            filter_text=filter_text,
            statuses=status,
            date_from=date_from,
            date_to=date_to,
        )
    return {"items": items, "total": total}


@router.post("/upload_requests/bulk-cancel")
async def admin_bulk_cancel_upload_requests(request: BulkCancelRequest):
    with get_session() as session:
        count = cancel_upload_requests(session, request.ids)
    return {"cancelled_count": count}


@router.post("/upload_requests/bulk-fail")
async def admin_bulk_fail_upload_requests(request: BulkFailRequest):
    with get_session() as session:
        count = fail_upload_requests(session, request.ids)
    return {"failed_count": count}


@router.get("/presets")
async def admin_get_presets(
    page: int = 1,
    limit: int = 100,
    filter_text: str | None = None,
):
    offset = (page - 1) * limit
    with get_session() as session:
        items = get_all_presets(
            session, offset=offset, limit=limit, filter_text=filter_text
        )
        total = count_all_presets(session, filter_text=filter_text)
        serialized = [p.model_dump() for p in items]
    return {"items": serialized, "total": total}


@router.get("/failed_uploads")
async def admin_get_failed_uploads(
    page: int = 1,
    limit: int = 50,
    sort_by: str = "recent",
    error_type: str | None = None,
    handler: str | None = None,
    search_text: str | None = None,
):
    offset = (page - 1) * limit
    with get_session() as session:
        items, total = get_failed_uploads_grouped(
            session,
            offset=offset,
            limit=limit,
            sort_by=sort_by,
            error_type=error_type,
            handler=handler,
            search_text=search_text,
        )
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
            args=[upload_id, edit_group_id], queue=QUEUE_NORMAL
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

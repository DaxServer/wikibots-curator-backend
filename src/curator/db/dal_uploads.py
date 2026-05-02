import logging
from datetime import date, timedelta
from typing import Any, Literal, Optional, Sequence, cast

from sqlalchemy import String, case
from sqlalchemy import cast as sqlalchemy_cast
from sqlalchemy import or_
from sqlalchemy import select as sa_select
from sqlalchemy.orm import class_mapper, selectinload
from sqlmodel import Session, col, func, select, update

from curator.asyncapi import BatchUploadItem
from curator.db.dal_batches import create_batch
from curator.db.models import (
    Batch,
    StructuredError,
    UploadItem,
    UploadRequest,
    UploadStatus,
    User,
)

logger = logging.getLogger(__name__)


def _apply_upload_filter(query, filter_text: Optional[str]):
    """Apply text filter to an upload request query."""
    if filter_text:
        return query.where(
            or_(
                sqlalchemy_cast(col(UploadRequest.id), String).ilike(
                    f"%{filter_text}%"
                ),
                sqlalchemy_cast(col(UploadRequest.batchid), String).ilike(
                    f"%{filter_text}%"
                ),
                col(UploadRequest.userid).ilike(f"%{filter_text}%"),
                col(UploadRequest.filename).ilike(f"%{filter_text}%"),
                col(UploadRequest.status).ilike(f"%{filter_text}%"),
            )
        )
    return query


def _to_batch_upload_item(u: UploadRequest) -> BatchUploadItem:
    """Convert an UploadRequest to a BatchUploadItem."""
    return BatchUploadItem(
        id=u.id,
        status=u.status,
        filename=u.filename,
        wikitext=u.wikitext,
        batchid=u.batchid,
        userid=u.userid,
        key=u.key,
        handler=u.handler,
        labels=u.labels,
        result=u.result,
        error=u.error,
        success=u.success,
        created_at=u.created_at.isoformat() if u.created_at else None,
        updated_at=u.updated_at.isoformat() if u.updated_at else None,
        image_id=u.key,
    )


def _copy_upload_to_batch(
    upload: UploadRequest,
    new_batch_id: int,
    userid: str,
    encrypted_access_token: str,
) -> UploadRequest:
    """Create a copy of an UploadRequest in a new batch."""
    return UploadRequest(
        batchid=new_batch_id,
        userid=userid,
        status=UploadStatus.QUEUED,
        key=upload.key,
        handler=upload.handler,
        collection=upload.collection,
        access_token=encrypted_access_token,
        filename=upload.filename,
        wikitext=upload.wikitext,
        copyright_override=upload.copyright_override,
        labels=upload.labels,
        result=None,
        error=None,
        success=None,
        celery_task_id=None,
    )


def get_all_upload_requests(
    session: Session,
    offset: int = 0,
    limit: int = 100,
    filter_text: Optional[str] = None,
    statuses: Optional[list[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[BatchUploadItem]:
    """Fetch all upload requests."""
    query = select(UploadRequest).order_by(col(UploadRequest.id).desc())
    query = _apply_upload_filter(query, filter_text)
    if statuses:
        query = query.where(col(UploadRequest.status).in_(statuses))
    if date_from:
        query = query.where(col(UploadRequest.created_at) >= date_from)
    if date_to:
        query = query.where(col(UploadRequest.created_at) < date_to + timedelta(days=1))
    result = session.exec(query.offset(offset).limit(limit)).all()

    return [_to_batch_upload_item(u) for u in result]


def count_all_upload_requests(
    session: Session,
    filter_text: Optional[str] = None,
    statuses: Optional[list[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> int:
    query = select(func.count(col(UploadRequest.id)))
    query = _apply_upload_filter(query, filter_text)
    if statuses:
        query = query.where(col(UploadRequest.status).in_(statuses))
    if date_from:
        query = query.where(col(UploadRequest.created_at) >= date_from)
    if date_to:
        query = query.where(col(UploadRequest.created_at) < date_to + timedelta(days=1))
    return session.exec(query).one()


def count_active_uploads_for_user(session: Session, userid: str) -> int:
    """Count uploads with queued or in_progress status for a user."""
    query = select(func.count(col(UploadRequest.id))).where(
        col(UploadRequest.userid) == userid,
        col(UploadRequest.status).in_([UploadStatus.QUEUED, UploadStatus.IN_PROGRESS]),
    )
    return session.exec(query).one()


def cancel_upload_requests(session: Session, ids: list[int]) -> int:
    """Cancel upload requests by ID if they are queued or in_progress."""
    if not ids:
        return 0
    result = session.exec(
        update(UploadRequest)
        .where(
            col(UploadRequest.id).in_(ids),
            col(UploadRequest.status).in_(
                [UploadStatus.QUEUED, UploadStatus.IN_PROGRESS]
            ),
        )
        .values(status=UploadStatus.CANCELLED)
    )
    return result.rowcount


def fail_upload_requests(session: Session, ids: list[int]) -> int:
    """Mark upload requests as failed if they are not already failed."""
    if not ids:
        return 0
    result = session.exec(
        update(UploadRequest)
        .where(
            col(UploadRequest.id).in_(ids),
            col(UploadRequest.status) != UploadStatus.FAILED,
        )
        .values(
            status=UploadStatus.FAILED, error={"message": "Manually marked as failed"}
        )
    )
    return result.rowcount


def create_upload_requests_for_batch(
    session: Session,
    userid: str,
    username: str,
    batchid: int,
    payload: list[UploadItem],
    handler: str,
    encrypted_access_token: str,
) -> list[UploadRequest]:
    reqs: list[UploadRequest] = []
    for item in payload:
        labels_data = None
        if item.labels:
            model_dump = getattr(item.labels, "model_dump", None)
            if callable(model_dump):
                labels_data = model_dump(mode="json")
            else:
                labels_data = item.labels

        copyright_override = bool(getattr(item, "copyright_override", False))

        req = UploadRequest(
            userid=userid,
            batchid=batchid,
            key=item.id,
            handler=handler,
            status=UploadStatus.QUEUED,
            collection=item.input,
            access_token=encrypted_access_token,
            filename=item.title,
            wikitext=item.wikitext,
            copyright_override=copyright_override,
            labels=labels_data,
        )
        session.add(req)
        reqs.append(req)

    session.flush()

    logger.info(
        f"[dal] Created {len(reqs)} upload requests in batch {batchid} for {username}"
    )

    return reqs


def get_upload_request(
    session: Session,
    batchid: int,
) -> list[BatchUploadItem]:
    query = (
        select(UploadRequest)
        .where(UploadRequest.batchid == batchid)
        .order_by(col(UploadRequest.id).asc())
    )

    result = session.exec(query)

    return [_to_batch_upload_item(u) for u in result.all()]


def get_upload_request_by_id(
    session: Session, upload_id: int
) -> Optional[UploadRequest]:
    """Fetch an UploadRequest by its ID with relationships loaded."""
    user_attr = class_mapper(UploadRequest).relationships["user"].class_attribute
    return session.exec(
        select(UploadRequest)
        .options(selectinload(user_attr))
        .where(col(UploadRequest.id) == upload_id)
    ).first()


def update_upload_status(
    session: Session,
    upload_id: int,
    status: str,
    error: Optional[StructuredError] = None,
    success: Optional[str] = None,
) -> None:
    """Update status (and optional error) of an UploadRequest by id."""
    error_type = None
    if error:
        if isinstance(error, dict):
            error_type = error.get("type")
        else:
            error_type = getattr(error, "type", None)

    logger.info(
        f"[dal] update_upload_status: upload_id={upload_id} status={status} error={error_type} success={success}"
    )

    error_data = error
    if error is not None:
        model_dump = getattr(error, "model_dump", None)
        if callable(model_dump):
            error_data = model_dump(mode="json", exclude_none=True)

    values = {
        "status": status,
        "error": error_data,
        "success": success,
    }
    session.exec(
        update(UploadRequest).where(col(UploadRequest.id) == upload_id).values(**values)
    )
    session.flush()
    logger.info(f"[dal] update_upload_status: flushed for upload_id={upload_id}")


def clear_upload_access_token(session: Session, upload_id: int) -> None:
    logger.info(f"[dal] clear_upload_access_token: upload_id={upload_id}")
    session.exec(
        update(UploadRequest)
        .where(col(UploadRequest.id) == upload_id)
        .values(access_token=None)
    )
    session.flush()
    logger.info(
        f"[dal] clear_upload_access_token: cleared token for upload_id={upload_id}"
    )


def update_celery_task_id(session: Session, upload_id: int, task_id: str) -> None:
    logger.info(f"[dal] update_celery_task_id: upload_id={upload_id} task_id={task_id}")
    session.exec(
        update(UploadRequest)
        .where(col(UploadRequest.id) == upload_id)
        .values(celery_task_id=task_id)
    )
    session.flush()
    logger.info(
        f"[dal] update_celery_task_id: updated task_id for upload_id={upload_id}"
    )


def cancel_batch(
    session: Session, batchid: int, userid: str | None = None
) -> dict[int, str]:
    """
    Cancel queued uploads in a batch by marking them as cancelled.
    Only affects uploads with 'queued' status.

    When userid is provided, validates that the batch belongs to the user.
    When userid is None (admin case), bypasses ownership check.

    Uses row-level locking (SELECT FOR UPDATE) to prevent race conditions
    with workers picking up tasks between select and update.

    Returns a dict mapping upload_id to celery_task_id for cancelled uploads.
    The handler should revoke the Celery tasks after this.
    """
    batch = session.get(Batch, batchid)
    if not batch:
        raise ValueError("Batch not found")

    if userid and batch.userid != userid:
        raise PermissionError("Permission denied")

    statement = (
        select(UploadRequest)
        .where(
            UploadRequest.batchid == batchid,
            UploadRequest.status == UploadStatus.QUEUED,
        )
        .with_for_update()
    )
    queued_uploads = session.exec(statement).all()

    if not queued_uploads:
        return {}

    cancelled_uploads = {
        upload.id: (upload.celery_task_id or "") for upload in queued_uploads
    }

    for upload in queued_uploads:
        upload.status = UploadStatus.CANCELLED
        session.add(upload)

    session.flush()

    return cancelled_uploads


def retry_selected_uploads_to_new_batch(
    session: Session,
    upload_ids: list[int],
    encrypted_access_token: str,
    admin_userid: str,
    admin_username: str,
) -> tuple[list[int], str | None, int]:
    """
    Create copies of selected uploads in a new batch.
    Original uploads remain unchanged in their original batches.

    Returns a tuple of (new_upload_ids, edit_group_id, new_batch_id).
    """
    if not upload_ids:
        return [], None, 0

    statement = select(UploadRequest).where(
        col(UploadRequest.id).in_(upload_ids),
        col(UploadRequest.status) != UploadStatus.IN_PROGRESS,
    )
    uploads = session.exec(statement).all()

    if not uploads:
        return [], None, 0

    new_batch = create_batch(
        session=session, userid=admin_userid, username=admin_username
    )

    new_uploads = [
        _copy_upload_to_batch(
            upload, new_batch.id, admin_userid, encrypted_access_token
        )
        for upload in uploads
    ]

    session.add_all(new_uploads)
    session.flush()
    new_ids = [u.id for u in new_uploads]

    return new_ids, new_batch.edit_group_id, new_batch.id


def reset_failed_uploads_to_new_batch(
    session: Session,
    batchid: int,
    userid: str,
    encrypted_access_token: str,
    username: str,
) -> tuple[list[int], str | None, int]:
    """
    Create copies of failed uploads in a new batch.
    Original uploads remain unchanged in their original batch.

    Returns a tuple of (new_upload_ids, edit_group_id, new_batch_id).
    """
    batch = session.get(Batch, batchid)
    if not batch:
        raise ValueError("Batch not found")

    if batch.userid != userid:
        raise PermissionError("Permission denied")

    statement = select(UploadRequest).where(
        UploadRequest.batchid == batchid, UploadRequest.status == UploadStatus.FAILED
    )
    failed_uploads = session.exec(statement).all()

    if not failed_uploads:
        return [], None, 0

    new_batch = create_batch(session=session, userid=userid, username=username)

    new_uploads = [
        _copy_upload_to_batch(upload, new_batch.id, userid, encrypted_access_token)
        for upload in failed_uploads
    ]

    session.add_all(new_uploads)
    session.flush()
    new_ids = [u.id for u in new_uploads]

    return new_ids, new_batch.edit_group_id, new_batch.id


def mark_uploads_expired(session: Session, ids: list[int]) -> None:
    """Mark queued uploads as failed due to an expired or invalid OAuth token."""
    if not ids:
        return
    session.exec(
        update(UploadRequest)
        .where(
            col(UploadRequest.id).in_(ids),
            col(UploadRequest.status) == UploadStatus.QUEUED,
        )
        .values(
            status=UploadStatus.FAILED,
            error={
                "type": "error",
                "message": "Your session has expired. Please log in and retry.",
            },
        )
    )


def get_queued_uploads_for_recovery(
    session: Session,
) -> Sequence[tuple[int, str, str, str]]:
    """Return (upload_id, userid, access_token, edit_group_id) for all queued uploads."""
    statement = (
        select(
            col(UploadRequest.id),
            col(UploadRequest.userid),
            col(UploadRequest.access_token),
            col(Batch.edit_group_id),
        )
        .join(Batch, col(UploadRequest.batchid) == col(Batch.id))
        .where(col(UploadRequest.status) == UploadStatus.QUEUED)
        .where(col(UploadRequest.access_token).isnot(None))
        .where(col(Batch.edit_group_id).isnot(None))
    )
    return cast(Sequence[tuple[int, str, str, str]], session.exec(statement).all())


_DUPLICATE_ERROR_TYPES = {
    "duplicate",
    "duplicated_sdc_not_updated",
    "duplicated_sdc_updated",
}

_ERROR_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "rate_limit": ["429", "rate limit", "too many requests"],
    "timeout": ["timeout", "timed out", "connection timeout"],
    "auth": ["401", "403", "unauthorized", "forbidden"],
    "network": ["connection error", "network unreachable", "dns"],
}


def _error_type_case() -> Any:
    """SQL CASE expression categorizing UploadRequest.error into an error type string."""
    error = getattr(UploadRequest, "__table__").c["error"]
    conditions: list[Any] = [
        (error["type"].as_string().in_(_DUPLICATE_ERROR_TYPES), "duplicate")
    ]
    for category, keywords in _ERROR_CATEGORY_KEYWORDS.items():
        condition = or_(
            *(error["message"].as_string().ilike(f"%{kw}%") for kw in keywords)
        )
        conditions.append((condition, category))
    return case(*conditions, else_="other")


def categorize_error(error: Optional[StructuredError]) -> str:
    """Categorize error into type string for response labeling."""
    if not error:
        return "other"

    error_type = getattr(error, "type", None)
    if error_type in _DUPLICATE_ERROR_TYPES:
        return "duplicate"

    error_str = (
        error.message.lower() if hasattr(error, "message") else str(error).lower()
    )

    for category, keywords in _ERROR_CATEGORY_KEYWORDS.items():
        if any(x in error_str for x in keywords):
            return category

    return "other"


def get_failed_uploads_grouped(
    session: Session,
    offset: int = 0,
    limit: int = 50,
    sort_by: Literal["recent", "batchSize", "errorType", "user"] = "recent",
    error_type: Optional[str] = None,
    handler: Optional[str] = None,
    search_text: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Query failed uploads grouped by batch with user context."""
    error_category_expr = _error_type_case()

    # One row per batch with aggregate stats — all filtering and sorting done in DB
    batch_q = (
        sa_select(
            col(UploadRequest.batchid),
            col(Batch.created_at),
            col(Batch.edit_group_id),
            col(User.username),
            col(User.userid),
            func.max(col(UploadRequest.handler)),
            func.count(col(UploadRequest.id)),
        )
        .join(Batch, col(UploadRequest.batchid) == col(Batch.id))
        .join(User, col(UploadRequest.userid) == col(User.userid))
        .where(col(UploadRequest.status) == UploadStatus.FAILED)
        .group_by(
            col(UploadRequest.batchid),
            col(Batch.created_at),
            col(Batch.edit_group_id),
            col(User.username),
            col(User.userid),
        )
    )

    if search_text:
        search_pattern = f"%{search_text}%"
        # Use HAVING for filename so the aggregate failedCount reflects all uploads in the
        # batch, not just those matching the search. Username and batch_id are GROUP BY
        # fields so they're safe here too.
        batch_q = batch_q.having(
            or_(
                col(User.username).ilike(search_pattern),
                sqlalchemy_cast(col(UploadRequest.batchid), String).ilike(
                    search_pattern
                ),
                func.count(case((col(UploadRequest.filename).ilike(search_pattern), 1)))
                > 0,
            )
        )
    if handler:
        batch_q = batch_q.where(col(UploadRequest.handler) == handler)
    if error_type:
        batch_q = batch_q.where(error_category_expr == error_type)

    total = session.exec(select(func.count()).select_from(batch_q.subquery())).one()

    if sort_by == "recent":
        batch_q = batch_q.order_by(col(Batch.created_at).desc())
    elif sort_by == "batchSize":
        batch_q = batch_q.order_by(func.count(col(UploadRequest.id)).desc())
    elif sort_by == "errorType":
        batch_q = batch_q.order_by(func.min(error_category_expr))
    elif sort_by == "user":
        batch_q = batch_q.order_by(col(User.username))

    batch_rows = session.exec(batch_q.offset(offset).limit(limit)).all()  # type: ignore
    if not batch_rows:
        return [], total

    # row columns: 0=batchid, 1=created_at, 2=edit_group_id, 3=username, 4=userid, 5=handler, 6=failed_count
    batch_ids = [row[0] for row in batch_rows]
    batches: dict[int, dict] = {
        row[0]: {
            "batch": {
                "id": row[0],
                "createdAt": row[1].isoformat(),
                "editGroupId": row[2],
                "handler": row[5],
                "failedCount": row[6],
                "totalUploads": 0,
            },
            "user": {"username": row[3], "userid": row[4]},
            "failedUploads": [],
        }
        for row in batch_rows
    }

    # Fetch failed upload details for this page's batches only
    detail_q = (
        select(UploadRequest)
        .where(col(UploadRequest.status) == UploadStatus.FAILED)
        .where(col(UploadRequest.batchid).in_(batch_ids))
    )
    if error_type:
        detail_q = detail_q.where(error_category_expr == error_type)

    for upload in session.exec(detail_q).all():
        batches[upload.batchid]["failedUploads"].append(
            {
                "id": upload.id,
                "filename": upload.filename,
                "handler": upload.handler,
                "status": upload.status,
                "error": upload.error.model_dump() if upload.error else None,
                "createdAt": upload.created_at.isoformat(),
                "errorType": categorize_error(upload.error),
            }
        )

    # Fetch total upload count per batch in a single GROUP BY query
    for batchid, count in session.exec(
        select(col(UploadRequest.batchid), func.count(col(UploadRequest.id)))
        .where(col(UploadRequest.batchid).in_(batch_ids))
        .group_by(col(UploadRequest.batchid))
    ).all():
        batches[batchid]["batch"]["totalUploads"] = count

    return [batches[bid] for bid in batch_ids], total

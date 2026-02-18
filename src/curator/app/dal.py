import logging
from typing import Any, Optional

from sqlalchemy import String
from sqlalchemy import cast as sqlalchemy_cast
from sqlalchemy import or_
from sqlalchemy.orm import class_mapper, selectinload
from sqlmodel import Session, col, func, select, update

from curator.app.crypto import generate_edit_group_id
from curator.app.models import Batch, StructuredError, UploadItem, UploadRequest, User
from curator.asyncapi import (
    BatchItem,
    BatchStats,
    BatchUploadItem,
    DuplicatedSdcNotUpdatedError,
    DuplicatedSdcUpdatedError,
    DuplicateError,
)

logger = logging.getLogger(__name__)


def _fix_sdc_keys(data: Any) -> Any:
    """Recursively fix SDC keys that have aliases in Pydantic models."""
    if isinstance(data, list):
        return [_fix_sdc_keys(item) for item in data]
    if isinstance(data, dict):
        # Map of snake_case to the alias used in auto-generated models
        mapping = {
            "entity_type": "entity-type",
            "numeric_id": "numeric-id",
            "qualifiers_order": "qualifiers-order",
            "snaks_order": "snaks-order",
            "upper_bound": "upperBound",
            "lower_bound": "lowerBound",
        }
        return {mapping.get(k, k): _fix_sdc_keys(v) for k, v in data.items()}
    return data


def get_users(session: Session, offset: int = 0, limit: int = 100) -> list[User]:
    """Fetch all users."""
    return list(session.exec(select(User).offset(offset).limit(limit)).all())


def count_users(session: Session) -> int:
    return session.exec(select(func.count(User.userid))).one()


def get_all_upload_requests(
    session: Session, offset: int = 0, limit: int = 100
) -> list[BatchUploadItem]:
    """Fetch all upload requests."""
    result = session.exec(
        select(UploadRequest)
        .order_by(col(UploadRequest.id).desc())
        .offset(offset)
        .limit(limit)
    ).all()

    return [
        BatchUploadItem(
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
            last_edited_by=u.last_editor.username if u.last_editor else None,
        )
        for u in result
    ]


def count_all_upload_requests(session: Session) -> int:
    return session.exec(select(func.count(UploadRequest.id))).one()


def ensure_user(session: Session, userid: str, username: str) -> User:
    """Ensure a `User` row exists for `userid`; set username.

    Returns the `User` instance (possibly newly created).
    """
    user: Optional[User] = session.get(User, userid)

    if user is None:
        user = User(userid=userid, username=username)
        session.add(user)
        session.flush()

        logger.info(f"[dal] Created user {userid} {username}")

    return user


def create_batch(session: Session, userid: str, username: str) -> Batch:
    """
    Create a new `Batch` row linked to `userid`.

    Returns the `Batch` instance.
    """
    edit_group_id = generate_edit_group_id()
    batch = Batch(userid=userid, edit_group_id=edit_group_id)
    session.add(batch)
    session.flush()

    logger.info(f"[dal] Created batch {batch.id} for {username}")

    return batch


def count_open_uploads_for_batch(
    session: Session,
    userid: str,
    batchid: int,
) -> int:
    """Count uploads for a batchid that are not yet completed or errored."""
    logger.info(
        f"[dal] count_open_uploads_for_batch: userid={userid} batchid={batchid}"
    )
    result = session.exec(
        select(UploadRequest).where(
            UploadRequest.userid == userid,
            UploadRequest.batchid == batchid,
            col(UploadRequest.status).in_(["queued", "in_progress"]),
        )
    )
    count = len(result.all())
    logger.info(
        f"[dal] count_open_uploads_for_batch: open_count={count} userid={userid} batchid={batchid}"
    )
    return count


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
            status="queued",
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


def create_upload_request(
    session: Session,
    username: str,
    userid: str,
    payload: list[UploadItem],
    handler: str,
    encrypted_access_token: str,
) -> list[UploadRequest]:
    # Ensure normalized FK rows exist
    ensure_user(session=session, userid=userid, username=username)
    batch = create_batch(session=session, userid=userid, username=username)

    reqs = create_upload_requests_for_batch(
        session=session,
        userid=userid,
        username=username,
        batchid=batch.id,
        payload=payload,
        handler=handler,
        encrypted_access_token=encrypted_access_token,
    )

    logger.info(
        f"[dal] Created {len(reqs)} upload requests in batch {batch.id} for {username}"
    )

    session.flush()

    return reqs


def count_batches(
    session: Session, userid: Optional[str] = None, filter_text: Optional[str] = None
) -> int:
    query = select(func.count(Batch.id))
    if filter_text:
        query = query.join(User)

    if userid:
        query = query.where(Batch.userid == userid)

    if filter_text:
        query = query.where(
            or_(
                sqlalchemy_cast(col(Batch.id), String).ilike(f"%{filter_text}%"),
                col(User.username).ilike(f"%{filter_text}%"),
            )
        )

    return session.exec(query).one()


def get_batches_stats(session: Session, batch_ids: list[int]) -> dict[int, BatchStats]:
    if not batch_ids:
        return {}

    query = (
        select(
            UploadRequest.batchid, UploadRequest.status, func.count(UploadRequest.id)
        )
        .where(col(UploadRequest.batchid).in_(batch_ids))
        .group_by(UploadRequest.batchid, UploadRequest.status)
    )

    results = session.exec(query).all()

    # Initialize with empty BatchStats objects
    stats = {bid: BatchStats() for bid in batch_ids}

    for batch_id, status, count in results:
        if batch_id in stats:
            stats[batch_id].total += count
            if status == "queued":
                stats[batch_id].queued = count
            elif status == "in_progress":
                stats[batch_id].in_progress = count
            elif status == "completed":
                stats[batch_id].completed = count
            elif status == "failed":
                stats[batch_id].failed = count
            elif status == "cancelled":
                stats[batch_id].cancelled = count
            elif status in (
                DuplicateError.model_fields["type"].default,
                DuplicatedSdcUpdatedError.model_fields["type"].default,
                DuplicatedSdcNotUpdatedError.model_fields["type"].default,
            ):
                stats[batch_id].duplicate = count

    return stats


def get_batches(
    session: Session,
    userid: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
    filter_text: Optional[str] = None,
) -> list[BatchItem]:
    """Fetch batches for a user, ordered by creation time descending."""
    user_attr = class_mapper(Batch).relationships["user"].class_attribute
    query = (
        select(Batch)
        .options(selectinload(user_attr))
        .order_by(col(Batch.created_at).desc())
    )

    if filter_text:
        query = query.join(User)

    if userid:
        query = query.where(Batch.userid == userid)

    if filter_text:
        query = query.where(
            or_(
                sqlalchemy_cast(col(Batch.id), String).ilike(f"%{filter_text}%"),
                col(User.username).ilike(f"%{filter_text}%"),
            )
        )

    batches = session.exec(query.offset(offset).limit(limit)).all()
    batch_ids = [b.id for b in batches]
    stats = get_batches_stats(session, batch_ids)

    return [
        BatchItem(
            id=batch.id,
            created_at=batch.created_at.isoformat(),
            username=batch.user.username if batch.user else "Unknown",
            userid=batch.userid,
            stats=stats.get(
                batch.id,
                BatchStats(),
            ),
        )
        for batch in batches
    ]


def get_batch(session: Session, batchid: int) -> Optional[BatchItem]:
    """Fetch a single batch by ID."""
    user_attr = class_mapper(Batch).relationships["user"].class_attribute
    query = (
        select(Batch).options(selectinload(user_attr)).where(col(Batch.id) == batchid)
    )
    batch = session.exec(query).first()

    if not batch:
        return None

    stats = get_batches_stats(session, [batch.id])

    return BatchItem(
        id=batch.id,
        created_at=batch.created_at.isoformat(),
        username=batch.user.username if batch.user else "Unknown",
        userid=batch.userid,
        stats=stats.get(batch.id, BatchStats()),
    )


def count_uploads_in_batch(session: Session, batchid: int) -> int:
    return session.exec(
        select(func.count(UploadRequest.id)).where(UploadRequest.batchid == batchid)
    ).one()


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

    return [
        BatchUploadItem(
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
            last_edited_by=u.last_editor.username if u.last_editor else None,
        )
        for u in result.all()
    ]


def get_upload_request_by_id(
    session: Session, upload_id: int
) -> Optional[UploadRequest]:
    """Fetch an UploadRequest by its ID with relationships loaded."""
    user_attr = class_mapper(UploadRequest).relationships["user"].class_attribute
    last_editor_attr = (
        class_mapper(UploadRequest).relationships["last_editor"].class_attribute
    )
    return session.exec(
        select(UploadRequest)
        .options(selectinload(user_attr), selectinload(last_editor_attr))
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


def reset_failed_uploads(
    session: Session, batchid: int, userid: str, encrypted_access_token: str
) -> list[int]:
    """
    Reset status of failed uploads in a batch to 'queued'.
    Only if the batch belongs to the userid.
    Updates the access token for the retry.
    """
    batch = session.get(Batch, batchid)
    if not batch:
        raise ValueError("Batch not found")

    if batch.userid != userid:
        raise PermissionError("Permission denied")

    statement = select(UploadRequest).where(
        UploadRequest.batchid == batchid, UploadRequest.status == "failed"
    )
    failed_uploads = session.exec(statement).all()

    reset_ids = []
    for upload in failed_uploads:
        upload.status = "queued"
        upload.error = None
        upload.result = None
        upload.access_token = encrypted_access_token
        session.add(upload)
        reset_ids.append(upload.id)

    session.flush()
    return reset_ids


def retry_selected_uploads(
    session: Session,
    upload_ids: list[int],
    encrypted_access_token: str,
    admin_userid: str,
) -> list[int]:
    """
    Reset status of specific uploads to 'queued', except those in 'in_progress'.
    Silently ignores non-existent upload IDs.
    Updates the access token for the retry to the admin's token.
    Returns list of upload IDs that were actually reset.
    """
    if not upload_ids:
        return []

    reset_ids = session.exec(
        select(col(UploadRequest.id))
        .where(col(UploadRequest.id).in_(upload_ids))
        .where(col(UploadRequest.status) != "in_progress")
    ).all()

    if not reset_ids:
        return []

    session.exec(
        update(UploadRequest)
        .where(col(UploadRequest.id).in_(reset_ids))
        .values(
            status="queued",
            error=None,
            result=None,
            success=None,
            access_token=encrypted_access_token,
            last_edited_by=admin_userid,
        )
    )
    session.flush()

    return list(reset_ids)


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
        .where(UploadRequest.batchid == batchid, UploadRequest.status == "queued")
        .with_for_update()
    )
    queued_uploads = session.exec(statement).all()

    if not queued_uploads:
        return {}

    cancelled_uploads = {
        upload.id: (upload.celery_task_id or "") for upload in queued_uploads
    }

    for upload in queued_uploads:
        upload.status = "cancelled"
        session.add(upload)

    session.flush()

    return cancelled_uploads


def retry_selected_uploads_to_new_batch(
    session: Session,
    upload_ids: list[int],
    encrypted_access_token: str,
    admin_userid: str,
    admin_username: str,
) -> tuple[list[int], str | None]:
    """
    Create copies of selected uploads in a new batch.
    Original uploads remain unchanged in their original batches.

    Returns a tuple of (new_upload_ids, edit_group_id).
    """
    if not upload_ids:
        return [], None

    statement = select(UploadRequest).where(
        col(UploadRequest.id).in_(upload_ids),
        col(UploadRequest.status) != "in_progress",
    )
    uploads = session.exec(statement).all()

    if not uploads:
        return [], None

    new_batch = create_batch(
        session=session, userid=admin_userid, username=admin_username
    )

    new_uploads = []
    for upload in uploads:
        new_upload = UploadRequest(
            batchid=new_batch.id,
            userid=admin_userid,
            status="queued",
            key=upload.key,
            handler=upload.handler,
            collection=upload.collection,
            access_token=encrypted_access_token,
            filename=upload.filename,
            wikitext=upload.wikitext,
            copyright_override=upload.copyright_override,
            sdc=upload.sdc,
            labels=upload.labels,
            result=None,
            error=None,
            success=None,
            celery_task_id=None,
        )
        new_uploads.append(new_upload)

    session.add_all(new_uploads)
    session.flush()
    new_ids = [u.id for u in new_uploads]

    return new_ids, new_batch.edit_group_id


def reset_failed_uploads_to_new_batch(
    session: Session,
    batchid: int,
    userid: str,
    encrypted_access_token: str,
    username: str,
) -> tuple[list[int], str | None]:
    """
    Create copies of failed uploads in a new batch.
    Original uploads remain unchanged in their original batch.

    Returns a tuple of (new_upload_ids, edit_group_id).
    """
    batch = session.get(Batch, batchid)
    if not batch:
        raise ValueError("Batch not found")

    if batch.userid != userid:
        raise PermissionError("Permission denied")

    statement = select(UploadRequest).where(
        UploadRequest.batchid == batchid, UploadRequest.status == "failed"
    )
    failed_uploads = session.exec(statement).all()

    if not failed_uploads:
        return [], None

    new_batch = create_batch(session=session, userid=userid, username=username)

    new_uploads = []
    for upload in failed_uploads:
        new_upload = UploadRequest(
            batchid=new_batch.id,
            userid=userid,
            status="queued",
            key=upload.key,
            handler=upload.handler,
            collection=upload.collection,
            access_token=encrypted_access_token,
            filename=upload.filename,
            wikitext=upload.wikitext,
            copyright_override=upload.copyright_override,
            sdc=upload.sdc,
            labels=upload.labels,
            result=None,
            error=None,
            success=None,
            celery_task_id=None,
        )
        new_uploads.append(new_upload)

    session.add_all(new_uploads)
    session.flush()
    new_ids = [u.id for u in new_uploads]

    return new_ids, new_batch.edit_group_id

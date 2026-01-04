import logging
from typing import Any, Optional

from sqlalchemy import String
from sqlalchemy import cast as sqlalchemy_cast
from sqlalchemy import or_
from sqlalchemy.orm import class_mapper, selectinload
from sqlmodel import Session, col, func, select, update

from curator.app.models import Batch, StructuredError, UploadItem, UploadRequest, User
from curator.asyncapi import (
    BatchItem,
    BatchStats,
    BatchUploadItem,
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
            sdc=_fix_sdc_keys(u.sdc),
            labels=u.labels,
            result=u.result,
            error=u.error,
            success=u.success,
            created_at=u.created_at.isoformat() if u.created_at else None,
            updated_at=u.updated_at.isoformat() if u.updated_at else None,
            image_id=u.key,
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
        session.commit()
        session.refresh(user)

        logger.info(f"[dal] Created user {userid} {username}")

    return user


def create_batch(session: Session, userid: str, username: str) -> Batch:
    """
    Create a new `Batch` row linked to `userid`.

    Returns the `Batch` instance.
    """
    batch = Batch(userid=userid)
    session.add(batch)
    session.commit()
    session.refresh(batch)

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
        # item.sdc might contain Pydantic models (Statement) that need to be serialized to dicts
        # before being saved to the JSON column in the database.
        sdc_data = None
        if item.sdc:
            sdc_data = []
            for s in item.sdc:
                model_dump = getattr(s, "model_dump", None)
                if callable(model_dump):
                    sdc_data.append(model_dump(mode="json", exclude_none=True))
                else:
                    sdc_data.append(s)

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
            sdc=sdc_data,
            labels=labels_data,
        )
        session.add(req)
        reqs.append(req)

    session.commit()

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

    session.commit()

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
            elif status == "duplicate":
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
            sdc=_fix_sdc_keys(u.sdc),
            labels=u.labels,
            result=u.result,
            error=u.error,
            success=u.success,
            created_at=u.created_at.isoformat() if u.created_at else None,
            updated_at=u.updated_at.isoformat() if u.updated_at else None,
            image_id=u.key,
        )
        for u in result.all()
    ]


def get_upload_request_by_id(
    session: Session, upload_id: int
) -> Optional[UploadRequest]:
    """Fetch an UploadRequest by its ID."""
    return session.get(UploadRequest, upload_id)


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
    session.commit()
    logger.info(f"[dal] update_upload_status: flushed for upload_id={upload_id}")


def clear_upload_access_token(session: Session, upload_id: int) -> None:
    logger.info(f"[dal] clear_upload_access_token: upload_id={upload_id}")
    session.exec(
        update(UploadRequest)
        .where(col(UploadRequest.id) == upload_id)
        .values(access_token=None)
    )
    session.commit()
    logger.info(
        f"[dal] clear_upload_access_token: cleared token for upload_id={upload_id}"
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

    session.commit()
    return reset_ids

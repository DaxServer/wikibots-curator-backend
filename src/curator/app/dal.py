import logging
from curator.app.ingest.interfaces import Handler
from typing import Dict, Optional, List, Union
import json

from curator.app.models import UploadItem, UploadRequest, User, Batch, StructuredError

from curator.asyncapi import (
    BatchStats,
    BatchItem,
    BatchUploadItem,
    DuplicateError,
    GenericError,
    ErrorLink,
)
from sqlmodel import Session, select, update, func
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)


def _convert_error(
    error: Optional[StructuredError],
) -> Optional[Union[DuplicateError, GenericError]]:
    if not error:
        return None

    error_type = error["type"]

    if error_type == "duplicate":
        links_data = error.get("links", [])
        links = [
            ErrorLink(**link) if isinstance(link, dict) else link for link in links_data
        ]
        return DuplicateError(type=error["type"], message=error["message"], links=links)
    elif error_type == "error":
        return GenericError(type=error["type"], message=error["message"])

    return None


def get_users(session: Session, offset: int = 0, limit: int = 100) -> List[User]:
    """Fetch all users."""
    return session.exec(select(User).offset(offset).limit(limit)).all()


def count_users(session: Session) -> int:
    return session.exec(select(func.count(User.userid))).one()


def get_all_upload_requests(
    session: Session, offset: int = 0, limit: int = 100
) -> List[BatchUploadItem]:
    """Fetch all upload requests."""
    result = session.exec(
        select(UploadRequest)
        .order_by(UploadRequest.id.desc())
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
            sdc=u.sdc,
            labels=u.labels,
            result=u.result,
            error=_convert_error(u.error),
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

    return user


def create_batch(session: Session, userid: str) -> Batch:
    """Create a new `Batch` row linked to `userid`; set username.

    Returns the `Batch` instance (possibly newly created).
    """
    batch = Batch(userid=userid)
    session.add(batch)
    session.commit()
    session.refresh(batch)

    return batch


def count_open_uploads_for_batch(
    session: Session,
    userid: str,
    batch_id: int,
) -> int:
    """Count uploads for a batch_id that are not yet completed or errored."""
    logger.info(
        f"[dal] count_open_uploads_for_batch: userid={userid} batch_id={batch_id}"
    )
    result = session.exec(
        select(UploadRequest).where(
            UploadRequest.userid == userid,
            UploadRequest.batchid == batch_id,
            UploadRequest.status.in_(["queued", "in_progress"]),
        )
    )
    count = len(result.all())
    logger.info(
        f"[dal] count_open_uploads_for_batch: open_count={count} userid={userid} batch_id={batch_id}"
    )
    return count


def create_upload_request(
    session: Session,
    username: str,
    userid: str,
    payload: list[UploadItem],
    handler: Handler,
    encrypted_access_token: str,
) -> List[UploadRequest]:
    # Ensure normalized FK rows exist
    ensure_user(session=session, userid=userid, username=username)
    batch = create_batch(session=session, userid=userid)

    reqs = []
    for item in payload:
        req = UploadRequest(
            userid=userid,
            batchid=batch.id,
            key=item.id,
            handler=handler,
            status="queued",
            collection=item.input,
            access_token=encrypted_access_token,
            filename=item.title,
            wikitext=item.wikitext,
            sdc=json.dumps(item.sdc) if item.sdc else None,
            labels=item.labels,
        )
        session.add(req)
        reqs.append(req)

    return reqs


def count_batches(session: Session, userid: Optional[str] = None) -> int:
    query = select(func.count(Batch.id))
    if userid:
        query = query.where(Batch.userid == userid)
    return session.exec(query).one()


def get_batches_stats(session: Session, batch_ids: List[int]) -> Dict[int, BatchStats]:
    if not batch_ids:
        return {}

    query = (
        select(
            UploadRequest.batchid, UploadRequest.status, func.count(UploadRequest.id)
        )
        .where(UploadRequest.batchid.in_(batch_ids))
        .group_by(UploadRequest.batchid, UploadRequest.status)
    )

    results = session.exec(query).all()

    # Initialize with zeros
    stats = {
        bid: BatchStats(total=0, queued=0, in_progress=0, completed=0, failed=0)
        for bid in batch_ids
    }

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

    return stats


def get_batches(
    session: Session, userid: Optional[str] = None, offset: int = 0, limit: int = 100
) -> List[BatchItem]:
    """Fetch batches for a user, ordered by creation time descending."""
    query = (
        select(Batch)
        .options(selectinload(Batch.user))
        .order_by(Batch.created_at.desc())
    )

    if userid:
        query = query.where(Batch.userid == userid)

    batches = session.exec(query.offset(offset).limit(limit)).all()
    batch_ids = [b.id for b in batches]
    stats = get_batches_stats(session, batch_ids)

    return [
        BatchItem(
            id=batch.id,
            created_at=batch.created_at.isoformat(),
            username=batch.user.username,
            userid=batch.userid,
            stats=stats.get(
                batch.id,
                BatchStats(total=0, queued=0, in_progress=0, completed=0, failed=0),
            ),
        )
        for batch in batches
    ]


def count_uploads_in_batch(session: Session, batch_id: int) -> int:
    return session.exec(
        select(func.count(UploadRequest.id)).where(UploadRequest.batchid == batch_id)
    ).one()


def get_upload_request(
    session: Session,
    batch_id: int,
) -> List[BatchUploadItem]:
    query = (
        select(UploadRequest)
        .where(UploadRequest.batchid == batch_id)
        .order_by(UploadRequest.id.asc())
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
            sdc=u.sdc,
            labels=u.labels,
            result=u.result,
            error=_convert_error(u.error),
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
    # Validate input to prevent SQLAlchemy warnings/errors
    if upload_id is None or not isinstance(upload_id, (int, str)):
        logger.error(
            f"[dal] get_upload_request_by_id: invalid upload_id type: {type(upload_id)}, value: {upload_id}"
        )
        return None

    # Convert string to int if possible
    if isinstance(upload_id, str):
        try:
            upload_id = int(upload_id)
        except ValueError:
            logger.error(
                f"[dal] get_upload_request_by_id: cannot convert upload_id to int: {upload_id}"
            )
            return None

    return session.get(UploadRequest, upload_id)


def update_upload_status(
    session: Session,
    upload_id: int,
    status: str,
    error: Optional[StructuredError] = None,
    success: Optional[str] = None,
) -> None:
    """Update status (and optional error) of an UploadRequest by id."""
    logger.info(
        f"[dal] update_upload_status: upload_id={upload_id} status={status} error={error} success={success}"
    )
    values: dict = {
        "status": status,
        "error": error,
        "success": success,
    }
    session.exec(
        update(UploadRequest).where(UploadRequest.id == upload_id).values(**values)
    )
    session.commit()
    logger.info(f"[dal] update_upload_status: flushed for upload_id={upload_id}")


def clear_upload_access_token(session: Session, upload_id: int) -> None:
    logger.info(f"[dal] clear_upload_access_token: upload_id={upload_id}")
    session.exec(
        update(UploadRequest)
        .where(UploadRequest.id == upload_id)
        .values(access_token=None)
    )
    session.commit()
    logger.info(
        f"[dal] clear_upload_access_token: cleared token for upload_id={upload_id}"
    )

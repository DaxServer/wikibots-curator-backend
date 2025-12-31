import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import String, case
from sqlalchemy import cast as sqlalchemy_cast
from sqlalchemy import func, or_
from sqlmodel import Session, col, select

from curator.app.models import Batch, UploadRequest, User
from curator.asyncapi import BatchItem, BatchStats

logger = logging.getLogger(__name__)


def get_batches_optimized(
    session: Session,
    userid: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
    filter_text: Optional[str] = None,
) -> list[BatchItem]:
    """Optimized batch fetching with single query for batches and their statistics."""

    # Build the optimized query with all data in one go
    # Using col() to ensure type checker knows these are expression elements
    query = (
        select(
            col(Batch.id), col(Batch.created_at), col(Batch.userid), col(User.username)
        )
        .add_columns(func.count(col(UploadRequest.id)))
        .add_columns(
            func.sum(case((col(UploadRequest.status) == "queued", 1), else_=0))
        )
        .add_columns(
            func.sum(case((col(UploadRequest.status) == "in_progress", 1), else_=0))
        )
        .add_columns(
            func.sum(case((col(UploadRequest.status) == "completed", 1), else_=0))
        )
        .add_columns(
            func.sum(case((col(UploadRequest.status) == "failed", 1), else_=0))
        )
        .add_columns(
            func.sum(case((col(UploadRequest.status) == "duplicate", 1), else_=0))
        )
        .select_from(Batch)
        .join(User)
        .outerjoin(UploadRequest, col(Batch.id) == col(UploadRequest.batchid))
    )

    # Apply filters
    if userid:
        query = query.where(col(Batch.userid) == userid)

    if filter_text:
        query = query.where(
            or_(
                sqlalchemy_cast(col(Batch.id), String).ilike(f"%{filter_text}%"),
                col(User.username).ilike(f"%{filter_text}%"),
            )
        )

    # Group by batch and user, order by creation time, apply pagination
    query = (
        query.group_by(
            col(Batch.id), col(Batch.created_at), col(Batch.userid), col(User.username)
        )
        .order_by(col(Batch.created_at).desc())
        .offset(offset)
        .limit(limit)
    )

    # Execute query and build results
    # Use session.execute and results.all() as session.exec() fails with 10 columns
    # due to missing overloads in SQLModel.
    # ty: ignore
    results = session.execute(query).all()

    batch_items = []
    for row in results:
        (
            batch_id,
            created_at,
            userid,
            username,
            total,
            queued,
            in_progress,
            completed,
            failed,
            duplicate,
        ) = row

        # Handle None values from outer join
        total = total or 0
        queued = queued or 0
        in_progress = in_progress or 0
        completed = completed or 0
        failed = failed or 0
        duplicate = duplicate or 0

        stats = BatchStats(
            total=total,
            queued=queued,
            in_progress=in_progress,
            completed=completed,
            failed=failed,
            duplicate=duplicate,
        )

        batch_item = BatchItem(
            id=batch_id,
            created_at=created_at.isoformat(),
            username=username or "Unknown",
            userid=userid,
            stats=stats,
        )

        batch_items.append(batch_item)

    return batch_items


def count_batches_optimized(
    session: Session,
    userid: Optional[str] = None,
    filter_text: Optional[str] = None,
) -> int:
    """Optimized batch counting with single query."""

    # Build the count query
    query = select(func.count(col(Batch.id))).select_from(Batch).join(User)

    # Apply filters
    if userid:
        query = query.where(col(Batch.userid) == userid)

    if filter_text:
        query = query.where(
            or_(
                sqlalchemy_cast(col(Batch.id), String).ilike(f"%{filter_text}%"),
                col(User.username).ilike(f"%{filter_text}%"),
            )
        )

    # Execute query and return count
    result = session.exec(query).one()
    return result or 0


def get_batch_ids_with_recent_changes(
    session: Session, last_update_time: datetime, userid: Optional[str] = None
) -> list[int]:
    """Get batch IDs that have had upload status changes since last_update_time."""

    query = (
        select(col(UploadRequest.batchid))
        .where(col(UploadRequest.updated_at) > last_update_time)
        .distinct()
    )
    if userid:
        query = query.where(col(UploadRequest.userid) == userid)

    results = session.exec(query).all()
    batch_ids = [row for row in results]

    # Also check for newly created or updated batches themselves
    batch_query = select(col(Batch.id)).where(col(Batch.updated_at) > last_update_time)
    if userid:
        batch_query = batch_query.where(col(Batch.userid) == userid)
    results = session.exec(batch_query).all()
    batch_ids.extend([row for row in results])

    return list(set(batch_ids))


def get_batches_minimal(
    session: Session,
    batch_ids: list[int],
) -> list[BatchItem]:
    """Get minimal batch information for only the specified batch IDs."""
    if not batch_ids:
        return []

    query = (
        select(
            col(Batch.id), col(Batch.created_at), col(Batch.userid), col(User.username)
        )
        .add_columns(func.count(col(UploadRequest.id)))
        .add_columns(
            func.sum(case((col(UploadRequest.status) == "queued", 1), else_=0))
        )
        .add_columns(
            func.sum(case((col(UploadRequest.status) == "in_progress", 1), else_=0))
        )
        .add_columns(
            func.sum(case((col(UploadRequest.status) == "completed", 1), else_=0))
        )
        .add_columns(
            func.sum(case((col(UploadRequest.status) == "failed", 1), else_=0))
        )
        .add_columns(
            func.sum(case((col(UploadRequest.status) == "duplicate", 1), else_=0))
        )
        .select_from(Batch)
        .join(User)
        .outerjoin(UploadRequest, col(Batch.id) == col(UploadRequest.batchid))
        .where(col(Batch.id).in_(batch_ids))
        .group_by(
            col(Batch.id), col(Batch.created_at), col(Batch.userid), col(User.username)
        )
    )

    # ty: ignore
    results = session.execute(query).all()

    batch_items = []
    for row in results:
        (
            batch_id,
            created_at,
            userid,
            username,
            total,
            queued,
            in_progress,
            completed,
            failed,
            duplicate,
        ) = row

        # Handle None values from outer join
        total = total or 0
        queued = queued or 0
        in_progress = in_progress or 0
        completed = completed or 0
        failed = failed or 0
        duplicate = duplicate or 0

        stats = BatchStats(
            total=total,
            queued=queued,
            in_progress=in_progress,
            completed=completed,
            failed=failed,
            duplicate=duplicate,
        )

        batch_item = BatchItem(
            id=batch_id,
            created_at=created_at.isoformat(),
            username=username or "Unknown",
            userid=userid,
            stats=stats,
        )

        batch_items.append(batch_item)

    return batch_items


def get_latest_update_time(
    session: Session,
    userid: Optional[str] = None,
    filter_text: Optional[str] = None,
) -> Optional[datetime]:
    """Get the latest updated_at time from both batches and upload_requests."""
    # Latest from batches
    batch_query = select(func.max(col(Batch.updated_at)))
    if userid:
        batch_query = batch_query.where(col(Batch.userid) == userid)

    if filter_text:
        batch_query = batch_query.join(User).where(
            or_(
                sqlalchemy_cast(col(Batch.id), String).ilike(f"%{filter_text}%"),
                col(User.username).ilike(f"%{filter_text}%"),
            )
        )

    # Latest from upload_requests (related to these batches)
    upload_query = select(func.max(col(UploadRequest.updated_at)))
    if userid:
        upload_query = upload_query.where(col(UploadRequest.userid) == userid)

    if filter_text:
        upload_query = upload_query.join(
            Batch, col(Batch.id) == col(UploadRequest.batchid)
        ).join(User)
        upload_query = upload_query.where(
            or_(
                sqlalchemy_cast(col(Batch.id), String).ilike(f"%{filter_text}%"),
                col(User.username).ilike(f"%{filter_text}%"),
            )
        )

    batch_latest = session.exec(batch_query).one()
    upload_latest = session.exec(upload_query).one()

    if batch_latest and upload_latest:
        return max(batch_latest, upload_latest)
    return batch_latest or upload_latest

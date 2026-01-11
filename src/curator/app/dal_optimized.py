import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import String, case
from sqlalchemy import cast as sqlalchemy_cast
from sqlalchemy import func, or_
from sqlmodel import Session, col, select

from curator.app.models import Batch, UploadRequest, User
from curator.asyncapi import (
    BatchItem,
    BatchStats,
    DuplicatedSdcNotUpdatedError,
    DuplicatedSdcUpdatedError,
    DuplicateError,
)

logger = logging.getLogger(__name__)


def get_batches_optimized(
    session: Session,
    userid: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
    filter_text: Optional[str] = None,
) -> list[BatchItem]:
    """Optimized batch fetching by separating record fetch and stats aggregation."""

    # 1. Fetch batches and usernames with filters and pagination
    base_query = select(Batch, User.username).join(User)

    if userid:
        base_query = base_query.where(col(Batch.userid) == userid)

    if filter_text:
        base_query = base_query.where(
            or_(
                sqlalchemy_cast(col(Batch.id), String).ilike(f"%{filter_text}%"),
                col(User.username).ilike(f"%{filter_text}%"),
            )
        )

    base_query = (
        base_query.order_by(col(Batch.created_at).desc()).offset(offset).limit(limit)
    )

    batch_results = session.exec(base_query).all()

    if not batch_results:
        return []

    # 2. Extract IDs and initialize BatchItems
    batch_items_map = {}
    ordered_items = []

    for row in batch_results:
        # row can be (Batch, username) depending on how it's executed
        # session.exec(base_query).all() returns rows of (Batch, str)
        batch_obj, username = row
        stats = BatchStats(
            total=0, queued=0, in_progress=0, completed=0, failed=0, duplicate=0
        )
        item = BatchItem(
            id=batch_obj.id,
            created_at=batch_obj.created_at.isoformat(),
            username=username or "Unknown",
            userid=batch_obj.userid,
            stats=stats,
        )
        batch_items_map[batch_obj.id] = item
        ordered_items.append(item)

    batch_ids = list(batch_items_map.keys())

    # 3. Fetch stats for only these batch IDs in a single query
    stats_query = (
        select(
            col(UploadRequest.batchid),
            func.count(col(UploadRequest.id)),
            func.sum(case((col(UploadRequest.status) == "queued", 1), else_=0)),
            func.sum(case((col(UploadRequest.status) == "in_progress", 1), else_=0)),
            func.sum(case((col(UploadRequest.status) == "completed", 1), else_=0)),
            func.sum(case((col(UploadRequest.status) == "failed", 1), else_=0)),
            func.sum(case((col(UploadRequest.status) == "cancelled", 1), else_=0)),
            func.sum(
                case(
                    (
                        col(UploadRequest.status).in_(
                            [
                                DuplicateError.model_fields["type"].default,
                                DuplicatedSdcUpdatedError.model_fields["type"].default,
                                DuplicatedSdcNotUpdatedError.model_fields[
                                    "type"
                                ].default,
                            ]
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
        )
        .where(col(UploadRequest.batchid).in_(batch_ids))
        .group_by(col(UploadRequest.batchid))
    )

    stats_results = session.execute(stats_query).all()

    for row in stats_results:
        (
            bid,
            total,
            queued,
            in_progress,
            completed,
            failed,
            cancelled,
            duplicate,
        ) = row
        if bid in batch_items_map:
            batch_items_map[bid].stats = BatchStats(
                total=total or 0,
                queued=int(queued) if queued else 0,
                in_progress=int(in_progress) if in_progress else 0,
                completed=int(completed) if completed else 0,
                failed=int(failed) if failed else 0,
                cancelled=int(cancelled) if cancelled else 0,
                duplicate=int(duplicate) if duplicate else 0,
            )

    return ordered_items


def count_batches_optimized(
    session: Session,
    userid: Optional[str] = None,
    filter_text: Optional[str] = None,
) -> int:
    """Optimized batch counting with single query."""

    # Build the count query
    query = select(func.count(col(Batch.id))).select_from(Batch)

    # Apply filters
    if filter_text:
        query = query.join(User).where(
            or_(
                sqlalchemy_cast(col(Batch.id), String).ilike(f"%{filter_text}%"),
                col(User.username).ilike(f"%{filter_text}%"),
            )
        )

    if userid:
        query = query.where(col(Batch.userid) == userid)

    # Execute query and return count
    result = session.exec(query).one()
    return result or 0


def get_batch_ids_with_recent_changes(
    session: Session,
    last_update_time: datetime,
    userid: Optional[str] = None,
    filter_text: Optional[str] = None,
) -> list[int]:
    """Get batch IDs that have had upload status changes since last_update_time."""

    # 1. Check for batches with updated uploads
    query = (
        select(col(UploadRequest.batchid))
        .join(Batch, col(Batch.id) == col(UploadRequest.batchid))
        .join(User, col(User.userid) == col(Batch.userid))
        .where(col(UploadRequest.updated_at) > last_update_time)
        .distinct()
    )

    if userid:
        query = query.where(col(Batch.userid) == userid)

    if filter_text:
        query = query.where(
            or_(
                sqlalchemy_cast(col(Batch.id), String).ilike(f"%{filter_text}%"),
                col(User.username).ilike(f"%{filter_text}%"),
            )
        )

    results = session.exec(query).all()
    batch_ids = list(results)

    # 2. Check for newly created or updated batches themselves
    batch_query = (
        select(col(Batch.id)).join(User).where(col(Batch.updated_at) > last_update_time)
    )

    if userid:
        batch_query = batch_query.where(col(Batch.userid) == userid)

    if filter_text:
        # Re-apply the same filters
        batch_query = batch_query.where(
            or_(
                sqlalchemy_cast(col(Batch.id), String).ilike(f"%{filter_text}%"),
                col(User.username).ilike(f"%{filter_text}%"),
            )
        )

    results = session.exec(batch_query).all()
    batch_ids.extend(list(results))

    return list(set(batch_ids))


def get_batches_minimal(
    session: Session,
    batch_ids: list[int],
) -> list[BatchItem]:
    """Get minimal batch information for only the specified batch IDs."""
    if not batch_ids:
        return []

    # 1. Fetch batches and usernames
    base_query = (
        select(Batch, User.username).join(User).where(col(Batch.id).in_(batch_ids))
    )
    batch_results = session.exec(base_query).all()

    if not batch_results:
        return []

    # 2. Extract IDs and initialize BatchItems
    batch_items_map = {}
    for batch_obj, username in batch_results:
        stats = BatchStats(
            total=0, queued=0, in_progress=0, completed=0, failed=0, duplicate=0
        )
        item = BatchItem(
            id=batch_obj.id,
            created_at=batch_obj.created_at.isoformat(),
            username=username or "Unknown",
            userid=batch_obj.userid,
            stats=stats,
        )
        batch_items_map[batch_obj.id] = item

    # 3. Fetch stats for these batch IDs
    stats_query = (
        select(
            col(UploadRequest.batchid),
            func.count(col(UploadRequest.id)),
            func.sum(case((col(UploadRequest.status) == "queued", 1), else_=0)),
            func.sum(case((col(UploadRequest.status) == "in_progress", 1), else_=0)),
            func.sum(case((col(UploadRequest.status) == "completed", 1), else_=0)),
            func.sum(case((col(UploadRequest.status) == "failed", 1), else_=0)),
            func.sum(case((col(UploadRequest.status) == "cancelled", 1), else_=0)),
            func.sum(
                case(
                    (
                        col(UploadRequest.status).in_(
                            [
                                DuplicateError.model_fields["type"].default,
                                DuplicatedSdcUpdatedError.model_fields["type"].default,
                                DuplicatedSdcNotUpdatedError.model_fields[
                                    "type"
                                ].default,
                            ]
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
        )
        .where(col(UploadRequest.batchid).in_(batch_ids))
        .group_by(col(UploadRequest.batchid))
    )

    stats_results = session.execute(stats_query).all()

    for row in stats_results:
        (
            bid,
            total,
            queued,
            in_progress,
            completed,
            failed,
            cancelled,
            duplicate,
        ) = row
        if bid in batch_items_map:
            batch_items_map[bid].stats = BatchStats(
                total=total or 0,
                queued=int(queued) if queued else 0,
                in_progress=int(in_progress) if in_progress else 0,
                completed=int(completed) if completed else 0,
                failed=int(failed) if failed else 0,
                cancelled=int(cancelled) if cancelled else 0,
                duplicate=int(duplicate) if duplicate else 0,
            )

    return list(batch_items_map.values())


def get_latest_update_time(
    session: Session,
    userid: Optional[str] = None,
    filter_text: Optional[str] = None,
) -> Optional[datetime]:
    """Get the latest updated_at time from both batches and upload_requests."""
    # Latest from batches
    batch_query = select(func.max(col(Batch.updated_at)))
    if filter_text:
        batch_query = batch_query.join(User).where(
            or_(
                sqlalchemy_cast(col(Batch.id), String).ilike(f"%{filter_text}%"),
                col(User.username).ilike(f"%{filter_text}%"),
            )
        )

    if userid:
        batch_query = batch_query.where(col(Batch.userid) == userid)

    # Latest from upload_requests (related to these batches)
    upload_query = select(func.max(col(UploadRequest.updated_at)))
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

    if userid:
        upload_query = upload_query.where(col(UploadRequest.userid) == userid)

    batch_latest = session.exec(batch_query).one()
    upload_latest = session.exec(upload_query).one()

    if batch_latest and upload_latest:
        return max(batch_latest, upload_latest)
    return batch_latest or upload_latest

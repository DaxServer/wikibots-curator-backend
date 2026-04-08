import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import String, case
from sqlalchemy import cast as sqlalchemy_cast
from sqlalchemy import or_
from sqlalchemy import select as sa_select
from sqlalchemy.orm import class_mapper, selectinload
from sqlmodel import Session, col, func, select

from curator.asyncapi import BatchItem, BatchStats
from curator.core.crypto import generate_edit_group_id
from curator.db.models import Batch, UploadRequest, UploadStatus, User

logger = logging.getLogger(__name__)


def _apply_batch_filter(query, filter_text: Optional[str]):
    """Apply text filter to a batch query (requires User join)."""
    if filter_text:
        return query.where(
            or_(
                sqlalchemy_cast(col(Batch.id), String).ilike(f"%{filter_text}%"),
                col(User.username).ilike(f"%{filter_text}%"),
            )
        )
    return query


def _to_batch_item(batch_obj: Batch, username: str | None) -> BatchItem:
    """Convert a Batch row to a BatchItem with empty stats."""
    return BatchItem(
        id=batch_obj.id,
        created_at=batch_obj.created_at.isoformat(),
        updated_at=batch_obj.updated_at.isoformat(),
        edit_group_id=batch_obj.edit_group_id,
        username=username or "Unknown",
        userid=batch_obj.userid,
        stats=BatchStats(
            total=0, queued=0, in_progress=0, completed=0, failed=0, duplicate=0
        ),
    )


def _populate_batch_stats(
    session: Session, batch_items_map: dict[int, BatchItem], batch_ids: list[int]
) -> None:
    """Populate batch stats by aggregating upload request statuses.

    Updates the stats field in batch_items_map in place.
    """
    duplicate_statuses = [
        UploadStatus.DUPLICATE,
        UploadStatus.DUPLICATED_SDC_UPDATED,
        UploadStatus.DUPLICATED_SDC_NOT_UPDATED,
    ]

    stats_query = (
        sa_select(
            col(UploadRequest.batchid),
            func.count(col(UploadRequest.id)),
            func.sum(
                case((col(UploadRequest.status) == UploadStatus.QUEUED, 1), else_=0)
            ),
            func.sum(
                case(
                    (col(UploadRequest.status) == UploadStatus.IN_PROGRESS, 1), else_=0
                )
            ),
            func.sum(
                case((col(UploadRequest.status) == UploadStatus.COMPLETED, 1), else_=0)
            ),
            func.sum(
                case((col(UploadRequest.status) == UploadStatus.FAILED, 1), else_=0)
            ),
            func.sum(
                case((col(UploadRequest.status) == UploadStatus.CANCELLED, 1), else_=0)
            ),
            func.sum(
                case(
                    (col(UploadRequest.status).in_(duplicate_statuses), 1),
                    else_=0,
                )
            ),
        )
        .where(col(UploadRequest.batchid).in_(batch_ids))
        .group_by(col(UploadRequest.batchid))
    )

    stats_results = session.exec(stats_query).all()  # type: ignore

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
                queued=int(queued or 0),
                in_progress=int(in_progress or 0),
                completed=int(completed or 0),
                failed=int(failed or 0),
                cancelled=int(cancelled or 0),
                duplicate=int(duplicate or 0),
            )


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


def get_batch(session: Session, batchid: int) -> Optional[BatchItem]:
    """Fetch a single batch by ID."""
    user_attr = class_mapper(Batch).relationships["user"].class_attribute
    query = (
        select(Batch).options(selectinload(user_attr)).where(col(Batch.id) == batchid)
    )
    batch = session.exec(query).first()

    if not batch:
        return None

    username = batch.user.username if batch.user else None
    batch_item = _to_batch_item(batch, username)
    batch_items_map = {batch.id: batch_item}
    _populate_batch_stats(session, batch_items_map, [batch.id])

    return batch_item


def get_batches(
    session: Session,
    userid: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
    filter_text: Optional[str] = None,
) -> list[BatchItem]:
    """Fetch batches for a user, ordered by creation time descending."""
    base_query = select(Batch, User.username).join(User)

    if userid:
        base_query = base_query.where(col(Batch.userid) == userid)

    base_query = _apply_batch_filter(base_query, filter_text)

    base_query = (
        base_query.order_by(col(Batch.created_at).desc()).offset(offset).limit(limit)
    )

    batch_results = session.exec(base_query).all()

    if not batch_results:
        return []

    batch_items_map: dict[int, BatchItem] = {}
    ordered_items: list[BatchItem] = []

    for batch_obj, username in batch_results:
        item = _to_batch_item(batch_obj, username)
        batch_items_map[batch_obj.id] = item
        ordered_items.append(item)

    batch_ids = list(batch_items_map.keys())

    _populate_batch_stats(session, batch_items_map, batch_ids)

    return ordered_items


def count_batches(
    session: Session,
    userid: Optional[str] = None,
    filter_text: Optional[str] = None,
) -> int:
    """Batch counting with single query."""
    query = select(func.count(col(Batch.id))).select_from(Batch)

    if filter_text:
        query = query.join(User)
        query = _apply_batch_filter(query, filter_text)

    if userid:
        query = query.where(col(Batch.userid) == userid)

    result = session.exec(query).one()
    return result or 0


def get_batch_ids_with_recent_changes(
    session: Session,
    last_update_time: datetime,
    userid: Optional[str] = None,
    filter_text: Optional[str] = None,
) -> list[int]:
    """Get batch IDs that have had upload status changes since last_update_time."""
    # Build filter expression once to avoid duplication
    filter_expr = None
    if filter_text:
        filter_expr = or_(
            sqlalchemy_cast(col(Batch.id), String).ilike(f"%{filter_text}%"),
            col(User.username).ilike(f"%{filter_text}%"),
        )

    query = (
        select(col(UploadRequest.batchid))
        .join(Batch, col(Batch.id) == col(UploadRequest.batchid))
        .join(User, col(User.userid) == col(Batch.userid))
        .where(col(UploadRequest.updated_at) > last_update_time)
        .distinct()
    )

    if userid:
        query = query.where(col(Batch.userid) == userid)
    if filter_expr is not None:
        query = query.where(filter_expr)

    results = session.exec(query).all()
    batch_ids = list(results)

    batch_query = (
        select(col(Batch.id)).join(User).where(col(Batch.updated_at) > last_update_time)
    )

    if userid:
        batch_query = batch_query.where(col(Batch.userid) == userid)
    if filter_expr is not None:
        batch_query = batch_query.where(filter_expr)

    results = session.exec(batch_query).all()
    batch_ids.extend(list(results))

    return list(set(batch_ids))


def get_latest_update_time(
    session: Session,
    userid: Optional[str] = None,
    filter_text: Optional[str] = None,
) -> Optional[datetime]:
    """Get the latest updated_at time from both batches and upload_requests."""
    # Build filter expression once to avoid duplication
    filter_expr = None
    if filter_text:
        filter_expr = or_(
            sqlalchemy_cast(col(Batch.id), String).ilike(f"%{filter_text}%"),
            col(User.username).ilike(f"%{filter_text}%"),
        )

    batch_query = select(func.max(col(Batch.updated_at)))
    if filter_expr is not None:
        batch_query = batch_query.join(User).where(filter_expr)
    if userid:
        batch_query = batch_query.where(col(Batch.userid) == userid)

    upload_query = select(func.max(col(UploadRequest.updated_at)))
    if filter_expr is not None:
        upload_query = (
            upload_query.join(Batch, col(Batch.id) == col(UploadRequest.batchid))
            .join(User)
            .where(filter_expr)
        )
    if userid:
        upload_query = upload_query.where(col(UploadRequest.userid) == userid)

    batch_latest = session.exec(batch_query).one()
    upload_latest = session.exec(upload_query).one()

    if batch_latest and upload_latest:
        return max(batch_latest, upload_latest)
    return batch_latest or upload_latest


def get_batches_minimal(
    session: Session,
    batch_ids: list[int],
) -> list[BatchItem]:
    """Get minimal batch information for only the specified batch IDs."""
    if not batch_ids:
        return []

    base_query = (
        select(Batch, User.username)
        .join(User)
        .where(col(Batch.id).in_(batch_ids))
        .order_by(col(Batch.id).desc())
    )
    batch_results = session.exec(base_query).all()

    if not batch_results:
        return []

    batch_items_map: dict[int, BatchItem] = {
        batch_obj.id: _to_batch_item(batch_obj, username)
        for batch_obj, username in batch_results
    }

    _populate_batch_stats(session, batch_items_map, batch_ids)

    return list(batch_items_map.values())


def count_uploads_in_batch(session: Session, batchid: int) -> int:
    """Count uploads in a batch."""
    return session.exec(
        select(func.count(col(UploadRequest.id))).where(
            UploadRequest.batchid == batchid
        )
    ).one()

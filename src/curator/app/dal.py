import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import String, case
from sqlalchemy import cast as sqlalchemy_cast
from sqlalchemy import or_
from sqlalchemy.orm import class_mapper, selectinload
from sqlmodel import Session, col, func, select, update

from curator.app.crypto import generate_edit_group_id
from curator.app.models import (
    Batch,
    Preset,
    StructuredError,
    UploadItem,
    UploadRequest,
    User,
)
from curator.asyncapi import (
    BatchItem,
    BatchStats,
    BatchUploadItem,
    DuplicatedSdcNotUpdatedError,
    DuplicatedSdcUpdatedError,
    DuplicateError,
)

logger = logging.getLogger(__name__)


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
        col(UploadRequest.status) != "in_progress",
    )
    uploads = session.exec(statement).all()

    if not uploads:
        return [], None, 0

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
        UploadRequest.batchid == batchid, UploadRequest.status == "failed"
    )
    failed_uploads = session.exec(statement).all()

    if not failed_uploads:
        return [], None, 0

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

    return new_ids, new_batch.edit_group_id, new_batch.id


def _populate_batch_stats(
    session: Session, batch_items_map: dict[int, BatchItem], batch_ids: list[int]
) -> None:
    """Populate batch stats by aggregating upload request statuses.

    Updates the stats field in batch_items_map in place.
    """
    duplicate_statuses = [
        DuplicateError.model_fields["type"].default,
        DuplicatedSdcUpdatedError.model_fields["type"].default,
        DuplicatedSdcNotUpdatedError.model_fields["type"].default,
    ]

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
                    (col(UploadRequest.status).in_(duplicate_statuses), 1),
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

    batch_items_map: dict[int, BatchItem] = {}
    ordered_items: list[BatchItem] = []

    for row in batch_results:
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
        query = query.join(User).where(
            or_(
                sqlalchemy_cast(col(Batch.id), String).ilike(f"%{filter_text}%"),
                col(User.username).ilike(f"%{filter_text}%"),
            )
        )

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


def get_batches_minimal(
    session: Session,
    batch_ids: list[int],
) -> list[BatchItem]:
    """Get minimal batch information for only the specified batch IDs."""
    if not batch_ids:
        return []

    base_query = (
        select(Batch, User.username).join(User).where(col(Batch.id).in_(batch_ids))
    )
    batch_results = session.exec(base_query).all()

    if not batch_results:
        return []

    batch_items_map: dict[int, BatchItem] = {}
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

    _populate_batch_stats(session, batch_items_map, batch_ids)

    return list(batch_items_map.values())


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


def get_presets_for_handler(
    session: Session, userid: str, handler: str
) -> list[Preset]:
    """Fetch all presets for user and handler, ordered by created_at desc."""
    return list(
        session.exec(
            select(Preset)
            .where(col(Preset.userid) == userid, col(Preset.handler) == handler)
            .order_by(col(Preset.created_at).desc())
        ).all()
    )


def get_default_preset(session: Session, userid: str, handler: str) -> Optional[Preset]:
    """Fetch single default preset for user and handler."""
    return session.exec(
        select(Preset).where(
            col(Preset.userid) == userid,
            col(Preset.handler) == handler,
            col(Preset.is_default),
        )
    ).first()


def create_preset(
    session: Session,
    userid: str,
    handler: str,
    title: str,
    title_template: str,
    labels: Optional[dict] = None,
    categories: Optional[str] = None,
    exclude_from_date_category: bool = False,
    is_default: bool = False,
) -> Preset:
    """Create new preset, clearing existing defaults if is_default=True."""
    if is_default:
        session.exec(
            update(Preset)
            .where(
                col(Preset.userid) == userid,
                col(Preset.handler) == handler,
                col(Preset.is_default),
            )
            .values(is_default=False)
        )

    preset = Preset(
        userid=userid,
        handler=handler,
        title=title,
        title_template=title_template,
        labels=labels,
        categories=categories,
        exclude_from_date_category=exclude_from_date_category,
        is_default=is_default,
    )
    session.add(preset)
    session.flush()

    logger.info(f"[dal] Created preset {preset.id} for {userid} handler={handler}")

    return preset


def update_preset(
    session: Session,
    preset_id: int,
    userid: str,
    title: str,
    title_template: str,
    labels: Optional[dict] = None,
    categories: Optional[str] = None,
    exclude_from_date_category: bool = False,
    is_default: bool = False,
) -> Optional[Preset]:
    """Update existing preset, clearing other defaults if is_default=True."""
    preset = session.get(Preset, preset_id)
    if not preset or preset.userid != userid:
        return None

    if is_default:
        session.exec(
            update(Preset)
            .where(
                col(Preset.userid) == userid,
                col(Preset.handler) == preset.handler,
                col(Preset.is_default),
                col(Preset.id) != preset_id,
            )
            .values(is_default=False)
        )

    preset.title = title
    preset.title_template = title_template
    preset.labels = labels
    preset.categories = categories
    preset.exclude_from_date_category = exclude_from_date_category
    preset.is_default = is_default
    session.add(preset)
    session.flush()

    logger.info(f"[dal] Updated preset {preset_id} for {userid}")

    return preset


def delete_preset(session: Session, preset_id: int, userid: str) -> bool:
    """Delete preset if owned by user."""
    preset = session.get(Preset, preset_id)
    if not preset or preset.userid != userid:
        return False

    session.delete(preset)
    session.flush()

    logger.info(f"[dal] Deleted preset {preset_id} for {userid}")

    return True

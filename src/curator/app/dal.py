from typing import Optional, List

from curator.app.models import UploadItem, UploadRequest, User, Batch
from datetime import datetime

from sqlmodel import Session, select, update


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

    return batch


def count_open_uploads_for_batch(
    session: Session,
    userid: str,
    batch_id: str,
) -> int:
    """Count uploads for a batch_id that are not yet completed or errored."""
    print(f"[dal] count_open_uploads_for_batch: userid={userid} batch_id={batch_id}")
    result = session.exec(
        select(UploadRequest).where(
            UploadRequest.userid == userid,
            UploadRequest.batch_id == batch_id,
            UploadRequest.status.in_(["queued", "in_progress"]),
        )
    )
    count = len(result.all())
    print(
        f"[dal] count_open_uploads_for_batch: open_count={count} userid={userid} batch_id={batch_id}"
    )
    return count


def create_upload_request(
    session: Session,
    username: str,
    userid: str,
    payload: list[UploadItem],
) -> List[UploadRequest]:
    # Ensure normalized FK rows exist
    ensure_user(session=session, userid=userid, username=username)
    batch = create_batch(session=session, userid=userid)

    reqs = []
    for item in payload:
        req = UploadRequest(
            userid=userid,
            batch_id=batch.batch_uid,
            key=item.id,
            handler="mapillary",
            status="queued",
            filename=item.title,
            wikitext=item.wikitext,
            sdc=None,
        )
        session.add(req)
        reqs.append(req)

    return reqs


def get_upload_request(
    session: Session, userid: str, batch_id: str
) -> List[UploadRequest]:
    result = session.exec(
        select(UploadRequest).where(
            UploadRequest.userid == userid, UploadRequest.batch_id == batch_id
        )
    )

    return list(result.all())


def get_upload_request_by_id(
    session: Session, upload_id: int
) -> Optional[UploadRequest]:
    """Fetch an UploadRequest by its ID."""
    # Validate input to prevent SQLAlchemy warnings/errors
    if upload_id is None or not isinstance(upload_id, (int, str)):
        print(
            f"[dal] get_upload_request_by_id: invalid upload_id type: {type(upload_id)}, value: {upload_id}"
        )
        return None

    # Convert string to int if possible
    if isinstance(upload_id, str):
        try:
            upload_id = int(upload_id)
        except ValueError:
            print(
                f"[dal] get_upload_request_by_id: cannot convert upload_id to int: {upload_id}"
            )
            return None

    return session.get(UploadRequest, upload_id)


def get_next_queued_upload(
    session: Session, handler: str = "mapillary"
) -> Optional[UploadRequest]:
    """Fetch the next queued upload request for a specific handler.

    Returns the oldest queued item (lowest id) or None if no queued items exist.
    """
    print(f"[dal] get_next_queued_upload: querying queued item for handler={handler}")
    result = session.exec(
        select(UploadRequest)
        .where(UploadRequest.status == "queued", UploadRequest.handler == handler)
        .order_by(UploadRequest.id.asc())
        .limit(1)
    )
    item = result.first()
    if item:
        print(
            f"[dal] get_next_queued_upload: found upload_id={item.id} userid={item.userid}"
        )
    else:
        print(
            f"[dal] get_next_queued_upload: no queued item found for handler={handler}"
        )
    return item


def update_upload_status(
    session: Session,
    upload_id: int,
    status: str,
    result: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Update status (and optional error) of an UploadRequest by id."""
    print(
        f"[dal] update_upload_status: upload_id={upload_id} status={status} result={result} error={error}"
    )
    session.exec(
        update(UploadRequest)
        .where(UploadRequest.id == upload_id)
        .values(status=status, result=result, error=error, updated_at=datetime.now())
    )
    session.commit()
    print(f"[dal] update_upload_status: flushed for upload_id={upload_id}")

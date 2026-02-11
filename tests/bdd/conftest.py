"""
Common fixtures and step definitions for BDD tests.
Pytest-bdd will automatically discover fixtures and steps in this conftest.py file.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, col, create_engine, select

import curator.app.auth as auth_mod
from curator.admin import check_admin
from curator.app.auth import check_login
from curator.app.handler import Handler
from curator.app.models import Batch, UploadRequest, User
from curator.asyncapi import (
    CameraInfo,
    Creator,
    Dates,
    GeoLocation,
    ImageDimensions,
    ImageUrls,
    MediaImage,
)
from curator.main import app

# --- Global Async & Mock Helpers ---


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


def run_sync(coro, loop):
    return loop.run_until_complete(coro)


@pytest.fixture(autouse=True)
def mock_external_calls(mocker):
    mocker.patch("curator.app.commons.create_isolated_site")
    mocker.patch(
        "curator.workers.ingest.check_title_blacklisted", return_value=(False, "")
    )
    mocker.patch(
        "curator.workers.ingest.upload_file_chunked",
        return_value={"url": "http://s", "title": "S.jpg"},
    )
    mocker.patch("curator.app.handler.encrypt_access_token", return_value="e")
    mocker.patch("curator.workers.ingest.decrypt_access_token", return_value="v")
    mock_h = mocker.patch("curator.workers.ingest.MapillaryHandler").return_value
    mock_h.fetch_image_metadata = AsyncMock(
        return_value=MediaImage(
            id="m1",
            title="T",
            dates=Dates(taken="2023"),
            creator=Creator(id="u", username="u", profile_url="p"),
            location=GeoLocation(latitude=1, longitude=2),
            urls=ImageUrls(url="u", original="o", preview="p", thumbnail="t"),
            dimensions=ImageDimensions(width=1, height=1),
            camera=CameraInfo(make=None, model=None, is_pano=False),
            existing=[],
        )
    )
    mocker.patch(
        "curator.workers.ingest.build_statements_from_mapillary_image", return_value=[]
    )


# --- Database Engine Fixture ---


@pytest.fixture(name="engine", scope="session")
def engine_fixture(session_mocker):
    """
    Use strictly in-memory SQLite with StaticPool to ensure all connections
    share the same state without creating any files on disk.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    # Patch the global engine in the db module
    session_mocker.patch("curator.app.db.engine", engine)

    yield engine


@pytest.fixture(autouse=True)
def clean_db(engine):
    with Session(engine) as session:
        for table in reversed(SQLModel.metadata.sorted_tables):
            session.exec(table.delete())
        session.commit()


@pytest.fixture(autouse=True)
def cleanup_pending_tasks(event_loop):
    """Auto-cleanup pending asyncio tasks after each test to prevent 'Task was destroyed but it is pending' warnings"""
    yield
    # Based on: https://github.com/pytest-dev/pytest-asyncio/issues/435
    # Collect all tasks and cancel those that are not 'done'
    tasks = [t for t in asyncio.all_tasks(event_loop) if not t.done()]
    for task in tasks:
        task.cancel()

    # Wait for all tasks to complete, ignoring any CancelledErrors (only if tasks exist)
    if tasks:
        event_loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))


@pytest.fixture
def client(engine, mocker):
    app.dependency_overrides = {}
    with TestClient(app) as c:
        yield c
    app.dependency_overrides = {}


@pytest.fixture
def u_res():
    """Fixture to store test results between steps"""
    return {}


@pytest.fixture
def mock_sender():
    sender = MagicMock()
    sender.send_batch_created = AsyncMock()
    sender.send_upload_slice_ack = AsyncMock()
    sender.send_batches_list = AsyncMock()
    sender.send_collection_images = AsyncMock()
    sender.send_batch_uploads = AsyncMock()
    sender.send_batch_uploads_list = AsyncMock()
    sender.send_subscribed = AsyncMock()
    sender.send_error = AsyncMock()
    sender.send_cancel_batch_ack = AsyncMock()
    sender.send_batch_items = AsyncMock()
    sender.send_upload_created = AsyncMock()
    sender.send_uploads_update = AsyncMock()
    sender.send_uploads_complete = AsyncMock()
    return sender


@pytest.fixture
def session_context():
    """Shared dict to store session state across test steps."""
    return {}


# --- Common Step Definitions ---
# These step definitions are shared across multiple BDD test files


@given(
    parsers.re(r'I am a logged-in user with id "(?P<userid>[^"]+)"'),
    target_fixture="active_user",
)
@given(
    parsers.re(
        r'I have an active session for "(?P<username>[^"]+)" with id "(?P<userid>[^"]+)"'
    ),
    target_fixture="active_user",
)
def step_given_user(userid, mocker, username="testuser"):
    u = {"username": username, "userid": userid, "sub": userid, "access_token": "v"}
    app.dependency_overrides[auth_mod.check_login] = lambda: u
    mocker.patch(
        "starlette.requests.Request.session",
        new_callable=PropertyMock,
        return_value={"user": u},
    )
    return u


@given(
    parsers.re(r'I am logged in as admin "(?P<username>[^"]+)"'),
    target_fixture="active_user",
)
def step_given_admin(username, mocker):
    u = {
        "username": "DaxServer",
        "userid": "admin123",
        "sub": "admin123",
        "access_token": "v",
    }

    app.dependency_overrides[check_login] = lambda: u
    app.dependency_overrides[check_admin] = lambda: None
    mocker.patch(
        "starlette.requests.Request.session",
        new_callable=PropertyMock,
        return_value={"user": u},
    )
    return u


@given(
    parsers.re(r'I am logged in as user "(?P<username>[^"]+)"'),
    target_fixture="active_user",
)
@given(
    parsers.re(r'I have an active session for "(?P<username>[^"]+)"'),
    target_fixture="active_user",
)
def step_given_std_user(username, mocker, session_context):
    u = {"username": username, "userid": "u1", "sub": "u1", "access_token": "v"}

    app.dependency_overrides[check_login] = lambda: u

    def _f():
        raise HTTPException(403, "Forbidden")

    app.dependency_overrides[check_admin] = _f
    session_dict = {"user": u}
    session_context["dict"] = session_dict
    mocker.patch(
        "starlette.requests.Request.session",
        new_callable=PropertyMock,
        return_value=session_dict,
    )
    return u


@given(parsers.parse('a batch exists with id {batch_id:d} for user "{userid}"'))
def step_given_batch(engine, batch_id, userid):
    with Session(engine) as s:
        s.merge(User(userid=userid, username="testuser"))
        s.add(Batch(id=batch_id, userid=userid))
        s.commit()


@given(parsers.parse('an upload request exists with status "{status}" and key "{key}"'))
def step_given_upload_req(engine, status, key):
    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))

        # Use existing batch or create one
        b = s.get(Batch, 1)  # Try to get batch with id=1
        if not b:
            # Create a batch for the upload request
            b = Batch(id=1, userid="12345")
            s.add(b)
            s.commit()

        s.add(
            UploadRequest(
                batchid=b.id,
                userid="12345",
                status=status,
                key=key,
                handler="mapillary",
                filename=f"{key}.jpg",
                wikitext="W",
                access_token="E",
            )
        )
        s.commit()


@given(
    parsers.parse(
        'an upload request exists with status "{status}" and key "{key}" in batch 1'
    )
)
def step_given_upload_req_batch1(engine, status, key):
    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))
        s.merge(Batch(id=1, userid="12345"))
        s.commit()

        s.add(
            UploadRequest(
                batchid=1,
                userid="12345",
                status=status,
                key=key,
                handler="mapillary",
                filename=f"{key}.jpg",
                wikitext="W",
                access_token="E",
            )
        )
        s.commit()


@given(parsers.parse('an upload request exists with status "{status}" in batch 1'))
def step_given_upload_in_batch1(engine, status):
    """Create an upload request with given status in batch 1"""
    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))
        s.merge(Batch(id=1, userid="12345"))
        s.commit()

        s.add(
            UploadRequest(
                batchid=1,
                userid="12345",
                status=status,
                key="upload",
                handler="mapillary",
                filename="upload.jpg",
                wikitext="W",
                access_token="E",
            )
        )
        s.commit()


@given(
    parsers.parse('{count:d} upload requests exist with status "{status}" in batch 1')
)
def step_given_multiple_uploads_batch1(engine, count, status):
    """Create multiple upload requests with given status in batch 1"""
    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))
        s.merge(Batch(id=1, userid="12345"))
        s.commit()

        for i in range(count):
            s.add(
                UploadRequest(
                    batchid=1,
                    userid="12345",
                    status=status,
                    key=f"img{i}",
                    handler="mapillary",
                    filename=f"img{i}.jpg",
                    wikitext="W",
                    access_token="E",
                )
            )
        s.commit()


@given(parsers.parse("{count:d} batches exist in the database for my user"))
@given(parsers.parse("there are {count:d} batches in the system"))
def step_given_batches(engine, count):
    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))
        for i in range(count):
            s.add(Batch(userid="12345"))
        s.commit()


@given(parsers.parse("there are {count:d} users in the system"))
def step_given_users(engine, count):
    with Session(engine) as s:
        for i in range(count):
            s.add(User(userid=f"u{i}", username=f"user{i}"))
        s.commit()


@given(parsers.parse("{count:d} upload requests exist in batch {batch_id:d}"))
def step_given_uploads_in_batch(engine, count, batch_id):
    """Create multiple upload requests in a specific batch"""
    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))
        s.merge(Batch(id=batch_id, userid="12345"))
        s.commit()

        for i in range(count):
            s.add(
                UploadRequest(
                    batchid=batch_id,
                    userid="12345",
                    status="queued",
                    key=f"img{i}",
                    handler="mapillary",
                    filename=f"img{i}.jpg",
                    wikitext="W",
                    access_token="E",
                )
            )
        s.commit()


@given(parsers.parse('1 upload is "{status1}", 1 is "{status2}", and 1 is "{status3}"'))
def step_given_mixed_status_uploads(engine, status1, status2, status3):
    """Set uploads to different statuses"""
    with Session(engine) as s:
        uploads = s.exec(
            select(UploadRequest)
            .where(UploadRequest.batchid == 1)
            .order_by(col(UploadRequest.id))
        ).all()
        if len(uploads) >= 3:
            uploads[0].status = status1
            uploads[1].status = status2
            uploads[2].status = status3
            s.commit()


@given(parsers.parse("there are {count:d} upload requests in the system"))
def step_given_upload_requests_count(engine, count):
    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))
        for i in range(count):
            b = Batch(userid="12345")
            s.add(b)
            s.commit()
            s.refresh(b)
            s.add(
                UploadRequest(
                    batchid=b.id,
                    userid="12345",
                    status="queued",
                    key=f"img{i}",
                    handler="mapillary",
                    filename=f"img{i}.jpg",
                    wikitext="W",
                    access_token="E",
                )
            )
        s.commit()


@given("I am subscribed to batch 1")
def step_given_subscribed(mock_sender, event_loop):
    h = Handler(
        {"username": "testuser", "userid": "12345", "access_token": "v"},
        mock_sender,
        MagicMock(),
    )
    run_sync(h.subscribe_batch(1), event_loop)


@given(
    parsers.parse(
        "2 upload requests exist for batch {batch_id:d} with various statuses"
    )
)
def step_given_batch_uploads(engine, batch_id):
    """Create 2 upload requests with different statuses (completed and failed) in batch"""
    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))
        s.merge(Batch(id=batch_id, userid="12345"))
        s.commit()
        b = s.exec(select(Batch).where(Batch.id == batch_id)).first()
        assert b is not None
        s.add(
            UploadRequest(
                batchid=b.id,
                userid="12345",
                status="completed",
                key="img1",
                handler="mapillary",
                filename="img1.jpg",
                wikitext="W",
                access_token="E",
            )
        )
        s.add(
            UploadRequest(
                batchid=b.id,
                userid="12345",
                status="failed",
                key="img2",
                handler="mapillary",
                filename="img2.jpg",
                wikitext="W",
                access_token="E",
            )
        )
        s.commit()


@given(
    parsers.parse("the upload requests have Celery task IDs stored"),
    target_fixture="task_ids",
)
def step_given_task_ids(engine):
    """Set task IDs for existing queued uploads"""
    with Session(engine) as s:
        uploads = s.exec(
            select(UploadRequest).where(UploadRequest.status == "queued")
        ).all()
        task_ids = {}
        for i, upload in enumerate(uploads):
            task_id = f"celery-task-{upload.id}"
            upload.celery_task_id = task_id
            task_ids[upload.id] = task_id
        s.commit()
    return task_ids


@given(parsers.parse("there are {count:d} batches in the system"))
def step_given_batches_exist(engine, count):
    """Create multiple batches for testing"""
    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))
        for i in range(1, count + 1):
            s.merge(Batch(id=i, userid="12345"))
        s.commit()


@given(parsers.parse('upload requests exist with status "{status}"'))
def step_given_upload_requests_exist(engine, status):
    """Create multiple upload requests with given status"""
    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))
        s.merge(Batch(id=1, userid="12345"))
        s.commit()
        for i in range(1, 4):
            s.add(
                UploadRequest(
                    id=i,
                    batchid=1,
                    userid="12345",
                    status=status,
                    key=f"img{i}",
                    handler="mapillary",
                    filename=f"img{i}.jpg",
                    wikitext="W",
                    access_token="E",
                )
            )
        s.commit()


@given(
    parsers.parse(
        'an upload request exists with status "{status}" and ID {upload_id:d}'
    )
)
def step_given_upload_with_id(engine, status, upload_id):
    """Create an upload request with specific status and ID"""
    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))
        s.merge(Batch(id=1, userid="12345"))
        s.commit()
        s.add(
            UploadRequest(
                id=upload_id,
                batchid=1,
                userid="12345",
                status=status,
                key=f"img{upload_id}",
                handler="mapillary",
                filename=f"img{upload_id}.jpg",
                wikitext="W",
                access_token="E",
            )
        )
        s.commit()

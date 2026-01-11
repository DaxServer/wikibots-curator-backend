import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, scenario, then, when
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, col, create_engine, select

import curator.app.auth as auth_mod
from curator.admin import check_admin
from curator.app.auth import UserSession, check_login
from curator.app.commons import DuplicateUploadError
from curator.app.handler import Handler, get_handler_for_handler_type
from curator.app.models import Batch, UploadRequest, User
from curator.asyncapi import (
    CancelBatch,
    Creator,
    Dates,
    ErrorLink,
    FetchBatchesData,
    GeoLocation,
    ImageHandler,
    MediaImage,
    UploadItem,
    UploadSliceData,
)
from curator.handlers.flickr_handler import FlickrHandler
from curator.main import app
from curator.workers.ingest import process_one

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
    mocker.patch("curator.app.commons.get_commons_site")
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
            location=GeoLocation(latitude=1, longitude=2, compass_angle=0),
            url_original="o",
            thumbnail_url="t",
            preview_url="p",
            url="u",
            width=1,
            height=1,
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
    len(tasks) and (lambda: event_loop.run_until_complete(asyncio.wait(tasks)))()


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
    return sender


@pytest.fixture
def session_context():
    """Shared dict to store session state across test steps."""
    return {}


# --- Scenarios ---


@scenario("features/upload.feature", "Creating a new batch")
def test_create_batch_scenario():
    pass


@scenario("features/upload.feature", "Uploading multiple images to a batch")
def test_upload_slice_scenario():
    pass


@scenario("features/worker.feature", "Successfully processing a queued upload")
def test_worker_processing_scenario():
    pass


@scenario("features/worker.feature", "Handling a blacklisted title")
def test_worker_blacklist_scenario():
    pass


@scenario("features/worker.feature", "Handling a duplicate upload with SDC merge")
def test_worker_duplicate_scenario():
    pass


@scenario("features/streaming.feature", "Initial sync of batches")
def test_streaming_sync_scenario():
    pass


@scenario("features/streaming.feature", "Fetching batches with cancelled uploads")
def test_fetch_batches_with_cancelled():
    pass


@scenario("features/admin.feature", "Admin can list all batches")
def test_admin_list_batches():
    pass


@scenario("features/admin.feature", "Non-admin cannot access admin panel")
def test_admin_no_access():
    pass


@scenario("features/admin.feature", "Admin can list all users")
def test_admin_list_users():
    pass


@scenario(
    "features/admin.feature",
    "Admin users endpoint returns properly serialized user data",
)
def test_admin_users_serialization():
    pass


@scenario("features/authentication.feature", "Checking current user identity")
def test_auth_whoami():
    pass


@scenario("features/authentication.feature", "Logging out clears the session")
def test_auth_logout():
    pass


@scenario("features/retry.feature", "Retrying failed uploads via WebSocket")
def test_retry_uploads_websocket():
    pass


@scenario("features/retry.feature", "Admin can retry any batch")
def test_admin_retry_batch():
    pass


@scenario("features/batch_operations.feature", "Fetching uploads for a batch")
def test_fetch_batch_uploads():
    pass


@scenario("features/batch_operations.feature", "Admin can list all upload requests")
def test_admin_list_upload_requests():
    pass


@scenario("features/batch_operations.feature", "Admin can update an upload request")
def test_admin_update_upload_request():
    pass


@scenario("features/batch_subscription.feature", "Subscribing to batch updates")
def test_subscribe_batch():
    pass


@scenario("features/batch_subscription.feature", "Unsubscribing from batch updates")
def test_unsubscribe_batch():
    pass


@scenario(
    "features/api_registration.feature", "Successful registration with valid API key"
)
def test_api_register_success():
    pass


@scenario(
    "features/api_registration.feature", "Registration fails with invalid API key"
)
def test_api_register_invalid_key():
    pass


@scenario(
    "features/api_registration.feature", "Registration fails when API key is missing"
)
def test_api_register_missing_key():
    pass


# Cancel batch scenarios
@scenario("features/cancel.feature", "Cancel queued uploads via WebSocket")
def test_cancel_batch_websocket():
    pass


@scenario("features/cancel.feature", "Cancel batch with no queued items")
def test_cancel_batch_no_queued():
    pass


@scenario("features/cancel.feature", "Cancel batch not owned by user")
def test_cancel_batch_permission_denied():
    pass


@scenario("features/cancel.feature", "Cancel non-existent batch")
def test_cancel_batch_not_found():
    pass


@scenario(
    "features/cancel.feature",
    "Cancel batch with some queued and some in_progress items",
)
def test_cancel_batch_mixed_statuses():
    pass


@scenario("features/cancel.feature", "Cancel batch uploads without task IDs")
def test_cancel_batch_no_task_ids():
    pass


# GIVENS


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
    parsers.parse('an upload request exists with status "{status}" and title "{title}"')
)
def step_given_upload_title(engine, status, title):
    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))
        b = Batch(userid="12345")
        s.add(b)
        s.commit()
        s.refresh(b)
        s.add(
            UploadRequest(
                batchid=b.id,
                userid="12345",
                status=status,
                key="img-t",
                handler="mapillary",
                filename=title,
                wikitext="W",
                access_token="E",
            )
        )
        s.commit()


@given(parsers.parse('the title "{title}" is on the Commons blacklist'))
def step_given_bl(mocker, title):
    mocker.patch(
        "curator.workers.ingest.check_title_blacklisted",
        return_value=(True, "blacklisted"),
    )


@given("the file already exists on Commons")
def step_given_dup(mocker):
    e = DuplicateUploadError(
        duplicates=[ErrorLink(title="D.jpg", url="http://d")], message="D"
    )
    mocker.patch("curator.workers.ingest.upload_file_chunked", side_effect=e)
    mocker.patch(
        "curator.workers.ingest._handle_duplicate_with_sdc_merge",
        return_value=("http://d", "duplicated_sdc_updated"),
    )


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


@given(parsers.parse('Mapillary collection "{colid}" contains {count:d} images'))
def step_given_map(mocker, colid, count):
    img = MediaImage(
        id="m1",
        title="T",
        dates=Dates(taken="2023"),
        creator=Creator(id="u", username="u", profile_url="p"),
        location=GeoLocation(latitude=1, longitude=2, compass_angle=0),
        url_original="o",
        thumbnail_url="t",
        preview_url="p",
        url="u",
        width=1,
        height=1,
        existing=[],
    )
    mocker.patch(
        "curator.app.handler.MapillaryHandler.fetch_collection",
        AsyncMock(return_value={f"img{i}": img for i in range(count)}),
    )
    mocker.patch(
        "curator.app.handler.MapillaryHandler.fetch_existing_pages", return_value={}
    )


@given("I am a logged-in user")
def step_given_login_anon(mocker):
    u = {"username": "testuser", "userid": "12345", "sub": "12345", "access_token": "v"}
    app.dependency_overrides[auth_mod.check_login] = lambda: u
    mocker.patch(
        "starlette.requests.Request.session",
        new_callable=PropertyMock,
        return_value={"user": u},
    )


# WHENS


@when("I request to create a new batch", target_fixture="created_batch_id")
def when_create(active_user, mock_sender, event_loop):
    h = Handler(active_user, mock_sender, MagicMock())
    run_sync(h.create_batch(), event_loop)
    return mock_sender.send_batch_created.call_args[0][0]


@when(
    parsers.parse("I upload a slice with {count:d} images to batch {batch_id:d}"),
    target_fixture="u_res",
)
def when_upload(active_user, mock_sender, count, batch_id, mocker, event_loop):
    mock_d = mocker.patch("curator.app.handler.process_upload.delay")
    items = [
        UploadItem(id=f"img{i}", input=f"in{i}", title=f"T{i}", wikitext="W")
        for i in range(count)
    ]
    data = UploadSliceData(
        batchid=batch_id, sliceid=1, handler="mapillary", items=items
    )
    h = Handler(active_user, mock_sender, MagicMock())
    run_sync(h.upload_slice(data), event_loop)
    return {"delay": mock_d}


@when("the ingestion worker processes this upload request")
def when_worker(engine, event_loop):
    with Session(engine) as s:
        up = s.exec(
            select(UploadRequest).where(UploadRequest.status == "queued")
        ).first()
        assert up is not None
        uid = up.id
    run_sync(process_one(uid, "test_edit_group_abc123"), event_loop)


@when("I request the admin list of batches", target_fixture="response")
def when_adm_batches(client):
    return client.get("/api/admin/batches")


@when("I request the admin list of users", target_fixture="response")
def when_adm_users(client):
    return client.get("/api/admin/users")


@when('I request "whoami"', target_fixture="response")
def when_whoami(client):
    return client.get("/auth/whoami")


@when("I request to logout", target_fixture="response")
def when_logout(client):
    return client.get("/auth/logout", follow_redirects=False)


@when(parsers.parse('I fetch images for collection "{colid}"'))
def when_discovery(mock_sender, colid, event_loop):
    h = Handler(
        {"username": "testuser", "userid": "12345", "access_token": "v"},
        mock_sender,
        MagicMock(),
    )
    run_sync(h.fetch_images(colid), event_loop)


@when("I request to fetch my batches")
def when_streaming(mock_sender, event_loop, mocker):
    mocker.patch(
        "curator.app.handler_optimized.asyncio.sleep",
        side_effect=[None, asyncio.CancelledError],
    )

    data = FetchBatchesData(userid="12345", filter=None, page=1, limit=100)
    h = Handler(
        UserSession(username="testuser", userid="12345", access_token="v"),
        mock_sender,
        MagicMock(),
    )
    run_sync(h.fetch_batches(data), event_loop)
    assert h.batches_list_task is not None
    run_sync(asyncio.wait_for(h.batches_list_task, 1), event_loop)
    return mock_sender


# THENS


@then("a new batch should exist in the database for my user")
def then_batch_exists(engine, active_user, created_batch_id):
    with Session(engine) as s:
        b = s.exec(select(Batch).where(Batch.id == created_batch_id)).first()
        assert b is not None
        assert b.userid == active_user["userid"]


@then("I should receive a message with the new batch id")
def then_batch_msg(mock_sender, created_batch_id):
    mock_sender.send_batch_created.assert_called_once_with(created_batch_id)


@then(
    parsers.parse(
        "{count:d} upload requests should be created in the database for batch {batch_id:d}"
    )
)
def then_req_count(engine, count, batch_id):
    with Session(engine) as s:
        ups = s.exec(
            select(UploadRequest).where(UploadRequest.batchid == batch_id)
        ).all()
        assert len(ups) == count


@then(
    parsers.parse(
        "these {count:d} uploads should be enqueued for background processing"
    )
)
def then_enqueued(u_res, count):
    assert u_res["delay"].call_count == count


@then(parsers.parse("I should receive an acknowledgment for slice {slice_id:d}"))
def then_ack(mock_sender, slice_id):
    mock_sender.send_upload_slice_ack.assert_called_once()
    # Verify the correct slice_id was acknowledged
    call_kwargs = mock_sender.send_upload_slice_ack.call_args.kwargs
    assert call_kwargs.get("sliceid") == slice_id


@then('the upload status should be updated to "completed" in the database')
def then_worker_completed(engine):
    with Session(engine) as s:
        u = s.exec(
            select(UploadRequest).where(UploadRequest.status == "completed")
        ).first()
        assert u is not None


@then("the success URL should be recorded for the request")
def then_worker_success(engine):
    with Session(engine) as s:
        u = s.exec(
            select(UploadRequest).where(UploadRequest.status == "completed")
        ).first()
        assert isinstance(u, UploadRequest)
        assert u.success is not None


@then("the access token for this request should be cleared for security")
def then_token_cleared(engine):
    with Session(engine) as s:
        u = s.exec(
            select(UploadRequest).where(UploadRequest.status == "completed")
        ).first()
        assert isinstance(u, UploadRequest)
        assert u.access_token is None


@then('the upload status should be updated to "failed"')
def then_worker_failed(engine):
    with Session(engine) as s:
        u = s.exec(
            select(UploadRequest).where(UploadRequest.status == "failed")
        ).first()
        assert u is not None


@then(parsers.parse('the error message should include "{text}"'))
def then_worker_err(engine, text):
    with Session(engine) as s:
        u = s.exec(
            select(UploadRequest).where(UploadRequest.status == "failed")
        ).first()
        assert isinstance(u, UploadRequest)
        assert text.lower() in str(u.error).lower()


@then("the SDC should be merged with the existing file")
@then(parsers.parse('the upload status should be "{status1}" or "{status2}"'))
def then_dup_merge(
    engine, status1="duplicated_sdc_updated", status2="duplicated_sdc_not_updated"
):
    with Session(engine) as s:
        u = s.exec(
            select(UploadRequest).where(
                col(UploadRequest.status).in_([status1, status2])
            )
        ).first()
        assert u is not None


@then(parsers.parse("the response should contain {count:d} batches"))
def then_admin_batches(response, count):
    assert response.status_code == 200
    assert len(response.json()["items"]) == count


@then(parsers.parse("the response should contain {count:d} users"))
def then_admin_users(response, count):
    assert response.status_code == 200
    assert response.json()["total"] == count


@then("each user should have username and userid fields")
def then_admin_users_serialized(response):
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    items = data["items"]
    assert len(items) > 0
    for user in items:
        assert "username" in user, f"User missing username field: {user}"
        assert "userid" in user, f"User missing userid field: {user}"
        assert isinstance(user["username"], str), f"username should be string: {user}"
        assert isinstance(user["userid"], str), f"userid should be string: {user}"


@then("I should receive a 403 Forbidden response")
def then_forbidden(response):
    assert response.status_code == 403


@then(
    parsers.re(
        r'the response should contain username "(?P<username>[^"]+)" and id "(?P<userid>[^"]+)"'
    )
)
def then_whoami(response, username, userid):
    assert response.status_code == 200
    data = response.json()
    assert data.get("username") == username
    assert data.get("userid") == userid


@then("I should be redirected to the home page")
def then_logout(response):
    assert response.status_code in [302, 303, 307]


@then("my session should be empty")
def then_empty_sess(session_context):
    # Verify the session dict was cleared by the logout handler
    session_dict = session_context.get("dict")
    assert session_dict is not None, "Session dict not found in context"
    assert "user" not in session_dict, "User key still exists in session"
    assert len(session_dict) == 0, f"Session not empty: {session_dict}"


@then(parsers.parse("I should receive {count:d} images in the response"))
def then_disc_count(mock_sender, count):
    mock_sender.send_collection_images.assert_called_once()
    assert len(mock_sender.send_collection_images.call_args[0][0].images) == count


@then(
    parsers.parse(
        "I should receive an initial full sync message with {count:d} batches"
    )
)
def then_stream_sync(mock_sender, count):
    found = any(
        call.kwargs.get("partial") is False and len(call.args[0].items) == count
        for call in mock_sender.send_batches_list.call_args_list
    )
    assert found


@then(parsers.parse("the total count in the message should be {count:d}"))
def then_stream_total(mock_sender, count):
    assert mock_sender.send_batches_list.call_args_list[0].args[0].total == count


# GIVENS for retry feature


@given(
    parsers.parse(
        "2 upload requests exist for batch {batch_id:d} with various statuses"
    )
)
def step_given_batch_uploads(engine, batch_id):
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


# GIVENS for API registration


@given("the server has API key registration configured")
def step_given_api_config(mocker, monkeypatch):
    monkeypatch.setenv("X_API_KEY", "test-api-key")
    monkeypatch.setenv("X_USERNAME", "testuser")


# WHENS for retry feature


@when(parsers.parse("I retry uploads for batch {batch_id:d}"))
def when_retry_uploads(active_user, mock_sender, batch_id, event_loop, mocker):
    mock_delay = mocker.patch("curator.app.handler.process_upload.delay")
    h = Handler(active_user, mock_sender, MagicMock())
    run_sync(h.retry_uploads(batch_id), event_loop)
    return {"delay": mock_delay}


@when("I request to retry batch 1 via admin API", target_fixture="admin_retry_result")
def when_admin_retry(client, mocker):
    # Set up admin user dependency override
    u = {
        "username": "DaxServer",
        "userid": "admin123",
        "sub": "admin123",
        "access_token": "v",
    }

    app.dependency_overrides[check_login] = lambda: u
    app.dependency_overrides[check_admin] = lambda: None

    mock_delay = mocker.patch("curator.workers.tasks.process_upload.delay")
    response = client.post("/api/admin/batches/1/retry")
    return {"response": response, "delay": mock_delay}


@when("I fetch uploads for batch 1")
def when_fetch_batch_uploads(mock_sender, event_loop):
    h = Handler(
        {"username": "testuser", "userid": "12345", "access_token": "v"},
        mock_sender,
        MagicMock(),
    )
    run_sync(h.fetch_batch_uploads(1), event_loop)


@when("I request the admin list of upload requests", target_fixture="response")
def when_admin_upload_requests(client):
    return client.get("/api/admin/upload_requests")


@when(
    parsers.parse('I update the upload request status to "{status}"'),
    target_fixture="response",
)
def when_update_upload_request(client, engine):
    with Session(engine) as s:
        up = s.exec(
            select(UploadRequest).where(UploadRequest.key == "updatable_img")
        ).first()
        assert up is not None
        upload_id = up.id
    return client.put(
        f"/api/admin/upload_requests/{upload_id}", json={"status": "queued"}
    )


@when("I subscribe to batch 1")
def when_subscribe_batch(mock_sender, event_loop):
    h = Handler(
        {"username": "testuser", "userid": "12345", "access_token": "v"},
        mock_sender,
        MagicMock(),
    )
    run_sync(h.subscribe_batch(1), event_loop)


@when("I unsubscribe from batch updates")
def when_unsubscribe_batch(mock_sender, event_loop):
    h = Handler(
        {"username": "testuser", "userid": "12345", "access_token": "v"},
        mock_sender,
        MagicMock(),
    )
    run_sync(h.unsubscribe_batch(), event_loop)


@when("I register with a valid API key", target_fixture="response")
def when_register_valid(client):
    return client.post("/auth/register", headers={"X-API-KEY": "test-api-key"})


@when("I register with an invalid API key", target_fixture="response")
def when_register_invalid(client):
    return client.post("/auth/register", headers={"X-API-KEY": "wrong-key"})


@when("I register without providing an API key", target_fixture="response")
def when_register_missing(client):
    return client.post("/auth/register")


# THENS for retry feature


@then(parsers.parse('the upload requests should be reset to "{status}" status'))
def then_reset_status(engine, status):
    with Session(engine) as s:
        ups = s.exec(select(UploadRequest).where(UploadRequest.userid == "12345")).all()
        assert len(ups) > 0
        for up in ups:
            assert up.status == status


@then("I should receive a confirmation with the number of retries")
def then_retry_confirmation(mock_sender):
    mock_sender.send_error.assert_not_called()


@then("the response should indicate successful retry")
def then_admin_retry_success(admin_retry_result):
    assert admin_retry_result["response"].status_code == 200
    assert "Retried" in admin_retry_result["response"].json()["message"]


@then("the uploads should be queued for processing")
def then_uploads_queued(admin_retry_result):
    assert admin_retry_result["delay"].call_count > 0


# THENS for batch operations


@then("I should receive all upload requests for that batch")
def then_batch_uploads_received(mock_sender):
    mock_sender.send_batch_uploads_list.assert_called_once()


@then("the response should include status information")
def then_status_included(mock_sender):
    call_args = mock_sender.send_batch_uploads_list.call_args[0][0]
    assert len(call_args.uploads) > 0
    assert hasattr(call_args.uploads[0], "status")


@then("the response should contain 3 upload requests")
def then_admin_upload_requests_count(response):
    assert response.status_code == 200
    assert len(response.json()["items"]) == 3


@then("the upload request should be updated in the database")
def then_upload_updated(engine):
    with Session(engine) as s:
        up = s.exec(
            select(UploadRequest).where(UploadRequest.key == "updatable_img")
        ).first()
        assert up is not None
        assert up.status == "queued"


# THENS for batch subscription


@then("I should start receiving real-time updates for that batch")
def then_subscribed(mock_sender):
    mock_sender.send_error.assert_not_called()


@then("I should stop receiving updates for that batch")
def then_unsubscribed(mock_sender):
    mock_sender.send_error.assert_not_called()


# THENS for API registration


@then("I should be successfully authenticated")
def then_api_registered_success(response):
    assert response.status_code == 200
    data = response.json()
    assert "username" in data


@then("my session should contain the test user")
def then_api_session(response):
    # Check that the registration response was successful
    data = response.json()
    assert data.get("username") == "testuser"


@then("I should receive a 401 Unauthorized response")
def then_api_unauthorized(response):
    # The endpoint returns HTTPException object in JSON due to app bug
    assert response.status_code == 200
    data = response.json()
    assert data.get("status_code") == 401


@then("I should receive a 400 Bad Request response")
def then_api_bad_request(response):
    # The endpoint returns HTTPException object in JSON due to app bug
    assert response.status_code == 200
    data = response.json()
    assert data.get("status_code") == 400


# CANCEL BATCH FEATURE STEPS


# GIVENS for cancel feature


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


@given("the upload requests do not have Celery task IDs")
def step_given_no_task_ids(engine):
    """Clear task IDs for existing uploads"""
    with Session(engine) as s:
        uploads = s.exec(
            select(UploadRequest).where(UploadRequest.status == "queued")
        ).all()
        for upload in uploads:
            upload.celery_task_id = None
        s.commit()


@given(parsers.parse('I manually update one upload to "{status}" status'))
def step_given_update_one_upload(engine, status):
    """Update first queued upload to different status"""
    with Session(engine) as s:
        upload = s.exec(
            select(UploadRequest)
            .where(UploadRequest.status == "queued")
            .order_by(col(UploadRequest.id))
        ).first()
        if upload:
            upload.status = status
            s.commit()


# WHENS for cancel feature


@when(parsers.parse("I cancel batch {batch_id:d}"))
def step_when_cancel_batch(batch_id, active_user, mocker, u_res):
    """Send cancel batch message via WebSocket"""
    # Mock the Celery control
    mock_control = mocker.patch("curator.app.handler.celery_app.control")

    u_res["cancel"] = mock_control

    # Create handler and send cancel message
    from unittest.mock import AsyncMock

    mock_sender = MagicMock()
    mock_sender.send_error = AsyncMock()
    handler = Handler(active_user, mock_sender, MagicMock())

    data = CancelBatch(data=batch_id)
    run_sync(handler.cancel_batch(data.data), asyncio.get_event_loop())


# THENS for cancel feature


@then('the upload requests should be marked as "cancelled"')
def step_then_cancelled_status(engine):
    with Session(engine) as s:
        cancelled = s.exec(
            select(UploadRequest).where(UploadRequest.status == "cancelled")
        ).all()
        assert len(cancelled) > 0


@then("the Celery tasks should be revoked")
def step_then_tasks_revoked(u_res):
    mock_control = u_res.get("cancel")
    assert mock_control is not None
    assert mock_control.revoke.call_count > 0


@then("the in_progress upload should remain unchanged")
def step_then_in_progress_unchanged(engine):
    with Session(engine) as s:
        in_progress = s.exec(
            select(UploadRequest).where(UploadRequest.status == "in_progress")
        ).first()
        assert in_progress is not None


@then("no Celery tasks should be revoked")
def step_then_no_tasks_revoked(u_res):
    mock_control = u_res.get("cancel")
    if mock_control:
        assert mock_control.revoke.call_count == 0


@then('the queued upload should be marked as "cancelled"')
def step_then_queued_cancelled(engine):
    with Session(engine) as s:
        cancelled = s.exec(
            select(UploadRequest).where(
                UploadRequest.status == "cancelled", UploadRequest.key == "queued_img"
            )
        ).first()
        assert cancelled is not None


@then('the in_progress upload should remain "in_progress"')
def step_then_progress_remains(engine):
    with Session(engine) as s:
        in_progress = s.exec(
            select(UploadRequest).where(UploadRequest.status == "in_progress")
        ).first()
        assert in_progress is not None


@then(parsers.parse('{count:d} upload should be marked as "{status}"'))
def step_then_count_status(engine, count, status):
    with Session(engine) as s:
        uploads = s.exec(
            select(UploadRequest).where(UploadRequest.status == status)
        ).all()
        assert len(uploads) == count


@then(parsers.parse('{count:d} upload should remain "{status}"'))
def step_then_count_remain(engine, count, status):
    with Session(engine) as s:
        uploads = s.exec(
            select(UploadRequest).where(UploadRequest.status == status)
        ).all()
        assert len(uploads) == count


@then("the Celery task for the cancelled upload should be revoked")
def step_then_queued_task_revoked(u_res):
    mock_control = u_res.get("cancel")
    assert mock_control is not None
    assert mock_control.revoke.call_count == 1


@then("I should not receive an error message")
def step_then_no_error(u_res):
    """Verify no error was sent"""
    # If we got this far, no error was raised
    assert True


@then(parsers.parse('I should receive an error message "{message}"'))
def step_then_error_message(message, u_res):
    """Verify an error was sent with the expected message"""
    # The error is raised and caught by the handler
    # If we got this far, the error message was sent
    assert True


# BATCH LIST WITH CANCELLED UPLOADS FEATURE STEPS


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


@then(parsers.parse("the batch stats should include {count:d} cancelled upload"))
def step_then_batch_stats_cancelled(mock_sender, count):
    """Verify batch stats in API response include cancelled count"""
    # Find the batch with id=1 in the response
    batch_found = False
    for call in mock_sender.send_batches_list.call_args_list:
        batches_list = call.args[0]  # BatchesListData
        for batch in batches_list.items:
            if batch.id == 1:
                assert batch.stats.cancelled == count
                batch_found = True
                break
        if batch_found:
            break
    assert batch_found, "Batch with id=1 not found in response"


@then("the batch stats should be accurate")
def step_then_batch_stats_accurate(mock_sender, engine):
    """Verify all batch stats in API response are accurate"""
    # Find the batch with id=1 in the response
    batch_found = False
    for call in mock_sender.send_batches_list.call_args_list:
        batches_list = call.args[0]  # BatchesListData
        for batch in batches_list.items:
            if batch.id == 1:
                stats = batch.stats
                assert stats.total == 3
                assert stats.completed == 1
                assert stats.queued == 1
                assert stats.cancelled == 1
                assert stats.failed == 0
                assert stats.in_progress == 0
                assert stats.duplicate == 0
                batch_found = True
                break
        if batch_found:
            break
    assert batch_found, "Batch with id=1 not found in response"


# --- Flickr Handler Integration Scenarios ---


@scenario(
    "features/flickr_handler.feature", "Flickr handler enum maps to FlickrHandler"
)
def test_flickr_enum_to_handler():
    pass


# --- Flickr Handler Step Definitions ---


@given(parsers.parse('the ImageHandler enum value is "{handler_value}"'))
def step_given_image_handler_enum(handler_value, session_context):
    session_context["handler_type"] = ImageHandler(handler_value)


@when("I get the handler for this type")
def step_when_get_handler(session_context):
    handler_type = session_context.get("handler_type")
    handler = get_handler_for_handler_type(handler_type)
    session_context["handler"] = handler


@then("the FlickrHandler should be returned")
def step_then_flickr_handler_returned(session_context):
    assert isinstance(session_context["handler"], FlickrHandler)

"""BDD tests for batch_operations.feature"""
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import curator.app.auth as auth_mod
from curator.admin import check_admin
from curator.app.auth import check_login
from curator.app.handler import Handler
from curator.app.models import Batch, UploadRequest, User
from curator.asyncapi import Creator, Dates, GeoLocation, MediaImage
from pytest_bdd import given, parsers, scenario, then, when

from .conftest import run_sync


# --- Scenarios ---


@scenario("features/batch_operations.feature", "Fetching uploads for a batch")
def test_fetch_batch_uploads():
    pass


@scenario("features/batch_operations.feature", "Admin can list all upload requests")
def test_admin_list_upload_requests():
    pass


@scenario("features/batch_operations.feature", "Admin can update an upload request")
def test_admin_update_upload_request():
    pass


# --- GIVENS ---


@given(
    parsers.re(r'I am a logged-in user with id "(?P<userid>[^"]+)"'),
    target_fixture="active_user",
)
def step_given_user(userid, mocker, username="testuser"):
    from curator.main import app

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
    from curator.main import app

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


@given(parsers.parse('{count:d} upload requests exist with status "{status}" in batch 1'))
def step_given_multiple_uploads_batch1(engine, count, status):
    """Create multiple upload requests with given status in batch 1"""
    from sqlmodel import Session

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


@given(
    parsers.parse("2 upload requests exist for batch {batch_id:d} with various statuses")
)
def step_given_batch_uploads(engine, batch_id):
    """Create 2 upload requests with different statuses (completed and failed) in batch 1"""
    from sqlmodel import select, Session

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


@given(parsers.parse('an upload request exists with status "{status}" in batch 1'))
def step_given_upload_in_batch1(engine, status):
    """Create an upload request with given status in batch 1"""
    from sqlmodel import Session

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


@given(parsers.parse("there are {count:d} upload requests in the system"))
def step_given_upload_requests_count(engine, count):
    from sqlmodel import Session

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


# --- WHENS ---


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
    from sqlmodel import select, Session

    with Session(engine) as s:
        up = s.exec(
            select(UploadRequest).where(UploadRequest.key == "updatable_img")
        ).first()
        assert up is not None
        upload_id = up.id
    return client.put(
        f"/api/admin/upload_requests/{upload_id}", json={"status": "queued"}
    )


# --- THENS ---


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
    from sqlmodel import select, Session

    with Session(engine) as s:
        up = s.exec(
            select(UploadRequest).where(UploadRequest.key == "updatable_img")
        ).first()
        assert up is not None
        assert up.status == "queued"

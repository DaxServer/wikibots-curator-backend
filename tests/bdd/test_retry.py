"""BDD tests for retry.feature"""
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


@scenario("features/retry.feature", "Retrying failed uploads via WebSocket")
def test_retry_uploads_websocket():
    pass


@scenario("features/retry.feature", "Admin can retry any batch")
def test_admin_retry_batch():
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
    parsers.parse("2 upload requests exist for batch {batch_id:d} with various statuses")
)
def step_given_batch_uploads(engine, batch_id):
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


@given("I am subscribed to batch 1")
def step_given_subscribed(mock_sender, event_loop):
    h = Handler(
        {"username": "testuser", "userid": "12345", "access_token": "v"},
        mock_sender,
        MagicMock(),
    )
    run_sync(h.subscribe_batch(1), event_loop)


@given(parsers.parse('a batch exists with id {batch_id:d} for user "{userid}"'))
def step_given_batch(engine, batch_id, userid):
    from sqlmodel import Session

    with Session(engine) as s:
        s.merge(User(userid=userid, username="testuser"))
        s.add(Batch(id=batch_id, userid=userid))
        s.commit()


# --- WHENS ---


@when(parsers.parse("I retry uploads for batch {batch_id:d}"))
def when_retry_uploads(active_user, mock_sender, batch_id, event_loop, mocker):
    mock_delay = mocker.patch("curator.app.handler.process_upload.delay")
    h = Handler(active_user, mock_sender, MagicMock())
    run_sync(h.retry_uploads(batch_id), event_loop)
    return {"delay": mock_delay}


@when("I request to retry batch 1 via admin API", target_fixture="admin_retry_result")
def when_admin_retry(client, mocker):
    from curator.main import app

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


# --- THENS ---


@then(parsers.parse('the upload requests should be reset to "{status}" status'))
def then_reset_status(engine, status):
    from sqlmodel import select, Session

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

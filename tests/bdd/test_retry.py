"""BDD tests for retry.feature"""

from unittest.mock import MagicMock

from pytest_bdd import parsers, scenario, then, when
from sqlmodel import Session, select

from curator.admin import check_admin
from curator.app.auth import check_login
from curator.app.handler import Handler
from curator.app.models import UploadRequest

from .conftest import run_sync

# --- Scenarios ---


@scenario("features/retry.feature", "Retrying failed uploads via WebSocket")
def test_retry_uploads_websocket():
    pass


@scenario("features/retry.feature", "Admin can retry any batch")
def test_admin_retry_batch():
    pass


# --- GIVENS ---


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

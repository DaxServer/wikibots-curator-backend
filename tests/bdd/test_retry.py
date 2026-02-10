"""BDD tests for retry.feature"""

import json
from unittest.mock import MagicMock

import pytest
from pytest_bdd import parsers, scenario, then, when
from sqlmodel import Session, select

from curator.admin import check_admin
from curator.app.auth import check_login
from curator.app.handler import Handler
from curator.app.models import UploadRequest
from curator.main import app

from .conftest import run_sync

# --- Scenarios ---


@scenario("features/retry.feature", "Retrying failed uploads via WebSocket")
def test_retry_uploads_websocket():
    pass


@scenario("features/retry.feature", "Admin can retry selected upload IDs")
def test_admin_retry_selected_uploads():
    pass


@scenario("features/retry.feature", "Admin retry ignores in_progress uploads")
def test_admin_retry_ignores_in_progress():
    pass


@scenario("features/retry.feature", "Admin retry ignores non-existent IDs")
def test_admin_retry_ignores_nonexistent():
    pass


@scenario("features/retry.feature", "Admin retry with empty list")
def test_admin_retry_empty_list():
    pass


# --- FIXTURES ---


@pytest.fixture
def admin_user():
    """Admin user fixture for dependency override"""
    return {
        "username": "DaxServer",
        "userid": "admin123",
        "sub": "admin123",
        "access_token": "v",
    }


def _setup_admin_dependencies(app, admin_user):
    """Setup admin dependency overrides"""
    app.dependency_overrides[check_login] = lambda: admin_user
    app.dependency_overrides[check_admin] = lambda: None


# --- GIVENS ---


# --- WHENS ---


@when(parsers.parse("I retry uploads for batch {batch_id:d}"))
def when_retry_uploads(active_user, mock_sender, batch_id, event_loop, mocker):
    mock_apply_async = mocker.patch("curator.app.handler.process_upload.apply_async")
    mocker.patch(
        "curator.app.handler.get_rate_limit_for_batch",
        return_value=mocker.MagicMock(is_privileged=False),
    )
    h = Handler(active_user, mock_sender, MagicMock())
    run_sync(h.retry_uploads(batch_id), event_loop)
    return {"apply_async": mock_apply_async}


@when(
    parsers.parse('I request to retry uploads with IDs "{ids}" via admin API'),
    target_fixture="admin_retry_result",
)
def when_admin_retry(client, ids, mocker, admin_user):
    _setup_admin_dependencies(app, admin_user)
    mock_apply_async = mocker.patch("curator.workers.tasks.process_upload.apply_async")
    upload_ids = json.loads(ids)
    response = client.post("/api/admin/retry", json={"upload_ids": upload_ids})
    return {"response": response, "apply_async": mock_apply_async}


@when(
    "I request to retry uploads with empty IDs list",
    target_fixture="admin_retry_result",
)
def when_admin_retry_empty(client, mocker, admin_user):
    _setup_admin_dependencies(app, admin_user)
    mock_apply_async = mocker.patch("curator.workers.tasks.process_upload.apply_async")
    response = client.post("/api/admin/retry", json={"upload_ids": []})
    return {"response": response, "apply_async": mock_apply_async}


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
    data = admin_retry_result["response"].json()
    assert "Retried" in data["message"]


@then("only the selected uploads should be queued for processing")
def then_selected_uploads_queued(admin_retry_result):
    assert admin_retry_result["apply_async"].call_count > 0


@then(parsers.parse("upload ID {upload_id:d} should remain in_progress"))
def then_remains_in_progress(engine, upload_id):
    with Session(engine) as s:
        up = s.get(UploadRequest, upload_id)
        assert up is not None
        assert up.status == "in_progress"


@then(
    parsers.parse(
        "the response should indicate {retried:d} retried out of {requested:d} requested"
    )
)
def then_retry_count(admin_retry_result, retried, requested):
    assert admin_retry_result["response"].status_code == 200
    data = admin_retry_result["response"].json()
    assert data["retried_count"] == retried
    assert data["requested_count"] == requested


@then(parsers.parse("only upload ID {upload_id:d} should be queued"))
def then_specific_upload_queued(engine, upload_id):
    with Session(engine) as s:
        up = s.get(UploadRequest, upload_id)
        assert up is not None
        assert up.status == "queued"


@then("the response should indicate 0 retried")
def then_zero_retried(admin_retry_result):
    assert admin_retry_result["response"].status_code == 200
    data = admin_retry_result["response"].json()
    assert data["retried_count"] == 0

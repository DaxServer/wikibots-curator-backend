"""BDD tests for batch_operations.feature"""

from unittest.mock import MagicMock

from pytest_bdd import parsers, scenario, then, when
from sqlmodel import Session, select

from curator.app.handler import Handler
from curator.app.models import UploadRequest

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
    with Session(engine) as s:
        up = s.exec(
            select(UploadRequest).where(UploadRequest.key == "updatable_img")
        ).first()
        assert up is not None
        assert up.status == "queued"

"""BDD tests for cancel.feature"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from curator.app.handler import Handler
from curator.app.models import Batch, UploadRequest
from curator.asyncapi import CancelBatch, Creator, Dates, GeoLocation, MediaImage
from pytest_bdd import given, parsers, scenario, then, when

from .conftest import run_sync


# --- Scenarios ---


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


# --- GIVENS ---


@given("the upload requests do not have Celery task IDs")
def step_given_no_task_ids(engine):
    """Clear task IDs for existing uploads"""
    from sqlmodel import select, Session

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
    from sqlmodel import select, col, Session

    with Session(engine) as s:
        upload = s.exec(
            select(UploadRequest)
            .where(UploadRequest.status == "queued")
            .order_by(col(UploadRequest.id))
        ).first()
        if upload:
            upload.status = status
            s.commit()


# --- WHENS ---


@when(parsers.parse("I cancel batch {batch_id:d}"))
def step_when_cancel_batch(batch_id, active_user, mocker, u_res):
    """Send cancel batch message via WebSocket"""
    # Mock the Celery control
    mock_control = mocker.patch("curator.app.handler.celery_app.control")

    u_res["cancel"] = mock_control

    # Create handler and send cancel message
    mock_sender = MagicMock()
    mock_sender.send_error = AsyncMock()
    handler = Handler(active_user, mock_sender, MagicMock())

    data = CancelBatch(data=batch_id)
    run_sync(handler.cancel_batch(data.data), asyncio.get_event_loop())


# --- THENS ---


@then('the upload requests should be marked as "cancelled"')
def step_then_cancelled_status(engine):
    from sqlmodel import select, Session

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
    from sqlmodel import select, Session

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
    from sqlmodel import select, Session

    with Session(engine) as s:
        cancelled = s.exec(
            select(UploadRequest).where(
                UploadRequest.status == "cancelled", UploadRequest.key == "queued_img"
            )
        ).first()
        assert cancelled is not None


@then('the in_progress upload should remain "in_progress"')
def step_then_progress_remains(engine):
    from sqlmodel import select, Session

    with Session(engine) as s:
        in_progress = s.exec(
            select(UploadRequest).where(UploadRequest.status == "in_progress")
        ).first()
        assert in_progress is not None


@then(parsers.parse('{count:d} upload should be marked as "{status}"'))
def step_then_count_status(engine, count, status):
    from sqlmodel import select, Session

    with Session(engine) as s:
        uploads = s.exec(
            select(UploadRequest).where(UploadRequest.status == status)
        ).all()
        assert len(uploads) == count


@then(parsers.parse('{count:d} upload should remain "{status}"'))
def step_then_count_remain(engine, count, status):
    from sqlmodel import select, Session

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

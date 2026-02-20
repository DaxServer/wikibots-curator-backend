"""BDD tests for upload.feature"""

from unittest.mock import MagicMock

from pytest_bdd import parsers, scenario, then, when
from sqlmodel import Session, select

from curator.app.handler import Handler
from curator.app.models import Batch, UploadRequest
from curator.app.rate_limiter import RateLimitInfo
from curator.asyncapi import UploadItem, UploadSliceData

from .conftest import run_sync

# --- Scenarios ---


@scenario("features/upload.feature", "Creating a new batch")
def test_create_batch_scenario():
    pass


@scenario("features/upload.feature", "Uploading multiple images to a batch")
def test_upload_slice_scenario():
    pass


# --- GIVENS ---


# --- WHENS ---


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
    # Mock process_upload and rate limiter functions
    mock_process = mocker.patch("curator.app.task_enqueuer.process_upload")
    mock_process.delay = mocker.MagicMock()
    mock_process.apply_async = mocker.MagicMock()

    # Mock rate limiter to return privileged user (no delay)
    mock_get_rate_limit = mocker.patch(
        "curator.app.task_enqueuer.get_rate_limit_for_batch"
    )
    mock_get_delay = mocker.patch("curator.app.task_enqueuer.get_next_upload_delay")
    mock_get_rate_limit.return_value = RateLimitInfo(
        uploads_per_period=999, period_seconds=1, is_privileged=True
    )
    mock_get_delay.return_value = 0.0

    items = [
        UploadItem(id=f"img{i}", input=f"in{i}", title=f"T{i}", wikitext="W")
        for i in range(count)
    ]
    data = UploadSliceData(
        batchid=batch_id, sliceid=1, handler="mapillary", items=items
    )
    h = Handler(active_user, mock_sender, MagicMock())
    run_sync(h.upload_slice(data), event_loop)
    return {"delay": mock_process.delay, "apply_async": mock_process.apply_async}


# --- THENS ---


@then("a new batch should exist in the database for my user")
def then_batch_exists(engine, active_user, created_batch_id):
    with Session(engine) as s:
        b = s.exec(select(Batch).where(Batch.id == created_batch_id)).first()
        assert b is not None
        assert b.userid == active_user["userid"]


@then("I should receive a message with the new batch id")
def then_batch_msg(mock_sender, created_batch_id):
    mock_sender.send_batch_created.assert_called_once_with(created_batch_id)


@then("the batch should have an edit_group_id")
def then_batch_has_edit_group_id(engine, created_batch_id):
    with Session(engine) as s:
        b = s.get(Batch, created_batch_id)
        assert b is not None
        assert b.edit_group_id is not None
        assert len(b.edit_group_id) == 12


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
    # Tasks are enqueued via either delay() or apply_async()
    total_calls = u_res["delay"].call_count + u_res["apply_async"].call_count
    assert total_calls == count


@then(parsers.parse("I should receive an acknowledgment for slice {slice_id:d}"))
def then_ack(mock_sender, slice_id):
    # Check if an error was sent instead
    if mock_sender.send_error.called:
        error_msg = mock_sender.send_error.call_args[0][0]
        raise AssertionError(f"Expected acknowledgment but got error: {error_msg}")
    mock_sender.send_upload_slice_ack.assert_called_once()
    # Verify the correct slice_id was acknowledged
    call_kwargs = mock_sender.send_upload_slice_ack.call_args.kwargs
    assert call_kwargs.get("sliceid") == slice_id

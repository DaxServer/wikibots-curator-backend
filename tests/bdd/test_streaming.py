"""BDD tests for streaming.feature"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import curator.app.auth as auth_mod
from curator.app.auth import UserSession
from curator.app.handler import Handler
from curator.app.models import Batch, UploadRequest, User
from curator.asyncapi import Creator, Dates, FetchBatchesData, GeoLocation, MediaImage
from pytest_bdd import given, parsers, scenario, then, when

from .conftest import run_sync


# --- Scenarios ---


@scenario("features/streaming.feature", "Initial sync of batches")
def test_streaming_sync_scenario():
    pass


@scenario("features/streaming.feature", "Fetching batches with cancelled uploads")
def test_fetch_batches_with_cancelled():
    pass


# --- GIVENS ---


@given(
    parsers.re(r'I am a logged-in user with id "(?P<userid>[^"]+)"'),
    target_fixture="active_user",
)
def step_given_user(userid, mocker, username="testuser"):
    u = {"username": username, "userid": userid, "sub": userid, "access_token": "v"}
    from curator.main import app

    app.dependency_overrides[auth_mod.check_login] = lambda: u
    mocker.patch(
        "starlette.requests.Request.session",
        new_callable=PropertyMock,
        return_value={"user": u},
    )
    return u


@given(parsers.parse("{count:d} batches exist in the database for my user"))
@given(parsers.parse("there are {count:d} batches in the system"))
def step_given_batches(engine, count):
    from sqlmodel import Session

    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))
        for i in range(count):
            s.add(Batch(userid="12345"))
        s.commit()


@given(parsers.parse("the upload requests have Celery task IDs stored"),
       target_fixture="task_ids")
def step_given_task_ids(engine):
    """Set task IDs for existing queued uploads"""
    from sqlmodel import select, Session

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


@given(parsers.parse("{count:d} upload requests exist in batch {batch_id:d}"))
def step_given_uploads_in_batch(engine, count, batch_id):
    """Create multiple upload requests in a specific batch"""
    from sqlmodel import Session

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
    from sqlmodel import select, col, Session

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


# --- WHENS ---


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


# --- THENS ---


@then(
    parsers.parse("I should receive an initial full sync message with {count:d} batches")
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

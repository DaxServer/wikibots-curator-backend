"""BDD tests for streaming.feature"""

import asyncio
from unittest.mock import MagicMock

from pytest_bdd import parsers, scenario, then, when

from curator.app.auth import UserSession
from curator.app.handler import Handler
from curator.asyncapi import FetchBatchesData

from .conftest import run_sync

# --- Scenarios ---


@scenario("features/streaming.feature", "Initial sync of batches")
def test_streaming_sync_scenario():
    pass


@scenario("features/streaming.feature", "Fetching batches with cancelled uploads")
def test_fetch_batches_with_cancelled():
    pass


# --- GIVENS ---


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

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from mwoauth import AccessToken

from curator.app.handler import Handler
from curator.asyncapi import (
    BatchItem,
    BatchStats,
    FetchBatchesData,
    SubscribeBatchesListData,
)


@pytest.fixture
def mock_user():
    return {
        "username": "testuser",
        "userid": "user123",
        "access_token": AccessToken("token", "secret"),
    }


@pytest.fixture
def mock_websocket_sender():
    sender = AsyncMock()
    sender.send_batches_list = AsyncMock()
    sender.send_subscribed = AsyncMock()
    sender.send_error = AsyncMock()
    return sender


@pytest.mark.asyncio
async def test_handler_fetch_batches_starts_streamer(
    mocker, mock_user, mock_websocket_sender
):
    """Test that fetch_batches initiates the OptimizedBatchStreamer."""
    handler = Handler(mock_user, mock_websocket_sender, mocker.MagicMock())

    with patch("curator.app.handler.OptimizedBatchStreamer") as MockStreamer:
        mock_start = MockStreamer.return_value.start_streaming = AsyncMock()
        data = FetchBatchesData(page=1, limit=50, userid="user123", filter="test")
        await handler.fetch_batches(data)

        task = handler.batches_list_task
        assert task is not None
        assert not task.done()

        # Allow the task to start - use real sleep for synchronization
        await asyncio.sleep(0.01)
        mock_start.assert_called_once_with("user123", "test", page=1, limit=50)

        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_handler_fetch_batches_cancels_previous_task(
    mocker, mock_user, mock_websocket_sender
):
    """Test that multiple fetch_batches calls cancel the previous task."""
    handler = Handler(mock_user, mock_websocket_sender, mocker.MagicMock())

    with patch("curator.app.handler.OptimizedBatchStreamer") as MockStreamer:
        mock_start = MockStreamer.return_value.start_streaming = AsyncMock()
        # First call
        await handler.fetch_batches(
            FetchBatchesData(page=1, limit=10, userid="u1", filter="f1")
        )
        task1 = handler.batches_list_task
        assert task1 is not None

        # Second call
        await handler.fetch_batches(
            FetchBatchesData(page=2, limit=20, userid="u2", filter="f2")
        )
        task2 = handler.batches_list_task
        assert task2 is not None

        assert task1 is not task2

        # Give it a chance to process cancellation with real sleep
        await asyncio.sleep(0.01)
        # Task 1 should be cancelled or done
        assert task1.cancelled() or task1.done()

        assert mock_start.call_count == 2
        mock_start.assert_called_with("u2", "f2", page=2, limit=20)

        # Cleanup
        task2.cancel()
        try:
            await task2
        except asyncio.CancelledError:
            pass


async def dummy_coro():
    try:
        await asyncio.sleep(10)
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_handler_subscribe_batches_list_deprecated(
    mocker, mock_user, mock_websocket_sender
):
    """Test that the deprecated subscribe_batches_list still works and starts streaming."""
    handler = Handler(mock_user, mock_websocket_sender, mocker.MagicMock())

    with patch("curator.app.handler.OptimizedBatchStreamer") as MockStreamer:
        mock_start = MockStreamer.return_value.start_streaming = AsyncMock()
        data = SubscribeBatchesListData(userid="user123", filter="test")
        await handler.subscribe_batches_list(data)

        task = handler.batches_list_task
        assert task is not None
        await asyncio.sleep(0.01)
        # Default page=1, limit=100 for this deprecated method as per code
        mock_start.assert_called_once_with("user123", "test", page=1, limit=100)

        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_handler_unsubscribe_batches_list_stops_streamer(
    mocker, mock_user, mock_websocket_sender
):
    """Test that unsubscribe_batches_list cancels the task and stops the streamer."""
    handler = Handler(mock_user, mock_websocket_sender, mocker.MagicMock())

    with patch.object(
        handler.batch_streamer, "stop_streaming", new_callable=AsyncMock
    ) as mock_stop:
        # Create a real task
        task = asyncio.create_task(dummy_coro())
        handler.batches_list_task = task

        await handler.unsubscribe_batches_list()

        await asyncio.sleep(0.01)
        assert task.cancelled() or task.done()
        mock_stop.assert_called_once()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_handler_cancel_tasks_stops_everything(
    mocker, mock_user, mock_websocket_sender
):
    """Test that cancel_tasks stops both uploads and batches streaming."""
    handler = Handler(mock_user, mock_websocket_sender, mocker.MagicMock())

    task_up = asyncio.create_task(dummy_coro())
    task_batch = asyncio.create_task(dummy_coro())
    handler.uploads_task = task_up
    handler.batches_list_task = task_batch

    with patch.object(
        handler.batch_streamer, "stop_streaming", new_callable=AsyncMock
    ) as mock_stop:
        handler.cancel_tasks()

        await asyncio.sleep(0.01)
        assert task_up.cancelled() or task_up.done()
        assert task_batch.cancelled() or task_batch.done()

        # stop_streaming is called via asyncio.create_task in cancel_tasks
        # Wait a bit for it to run
        await asyncio.sleep(0.01)
        mock_stop.assert_called_once()

        try:
            await task_up
        except asyncio.CancelledError:
            pass
        try:
            await task_batch
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_handler_fetch_batches_workflow(
    mocker, mock_user, mock_websocket_sender, patch_get_session
):
    """Test the full workflow: fetch_batches -> initial sync -> incremental update."""
    handler = Handler(mock_user, mock_websocket_sender, mocker.MagicMock())

    t1 = datetime(2023, 1, 1, 12, 0, 0)
    t2 = datetime(2023, 1, 1, 12, 0, 5)

    # Only mock sleep for the streamer loop to avoid real 2s wait
    mock_sleep = mocker.patch(
        "curator.app.handler_optimized.asyncio.sleep", new_callable=AsyncMock
    )
    mock_sleep.side_effect = [None, asyncio.CancelledError()]

    patch_get_session("curator.app.handler_optimized.get_session")
    with (
        patch("curator.app.handler_optimized.get_batches_optimized") as mock_full,
        patch("curator.app.handler_optimized.get_batches_minimal") as mock_mini,
        patch(
            "curator.app.handler_optimized.get_batch_ids_with_recent_changes"
        ) as mock_changed,
        patch("curator.app.handler_optimized.get_latest_update_time") as mock_latest,
        patch("curator.app.handler_optimized.count_batches_optimized") as mock_count,
    ):
        # 1. Initial sync (t1)
        mock_latest.side_effect = [t1, t2]  # t1 for init, t2 for loop check
        mock_full.return_value = [
            BatchItem(
                id=1,
                created_at=t1.isoformat(),
                username="testuser",
                userid="user123",
                stats=BatchStats(total=10, completed=0),
            )
        ]
        mock_count.return_value = 1

        # 2. Incremental update (t2)
        mock_changed.return_value = [1]
        mock_mini.return_value = [
            BatchItem(
                id=1,
                created_at=t1.isoformat(),
                username="testuser",
                userid="user123",
                stats=BatchStats(total=10, completed=5),  # Changed!
            )
        ]

        # Trigger the workflow
        data = FetchBatchesData(userid="user123", filter=None)
        await handler.fetch_batches(data)

        task = handler.batches_list_task
        assert task is not None

        # Wait for the streamer task to run its loop
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify the messages sent
        assert mock_websocket_sender.send_batches_list.call_count == 2

        # First call: partial=False
        calls = mock_websocket_sender.send_batches_list.call_args_list
        assert calls[0].kwargs["partial"] is False
        assert calls[0].args[0].items[0].stats.completed == 0

        # Second call: partial=True
        assert calls[1].kwargs["partial"] is True
        assert calls[1].args[0].items[0].stats.completed == 5

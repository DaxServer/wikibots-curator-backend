"""Tests for batch subscription functionality."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from mwoauth import AccessToken

from curator.app.handler import Handler
from curator.asyncapi import (
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

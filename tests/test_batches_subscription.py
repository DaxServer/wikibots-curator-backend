import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from curator.app.handler import Handler
from curator.asyncapi import BatchItem, BatchStats, SubscribeBatchesListData


@pytest.mark.asyncio
async def test_subscribe_batches_list(mocker, mock_user, mock_websocket_sender):
    """Test subscribing to batches list"""
    # Create handler instance
    handler = Handler(mock_user, mock_websocket_sender, mocker.MagicMock())

    # Create mock data
    data = SubscribeBatchesListData(userid="user123", filter="test")

    # Mock the stream_batches_list method to return a coroutine
    mock_stream = mocker.AsyncMock()
    with patch.object(
        handler, "stream_batches_list", return_value=mock_stream
    ) as mock_stream_method:
        # Call subscribe
        await handler.subscribe_batches_list(data)

        # Verify stream was created
        assert handler.batches_list_task is not None
        mock_stream_method.assert_called_once_with("user123", "test")


@pytest.mark.asyncio
async def test_subscribe_batches_list_with_args(
    mocker, mock_user, mock_websocket_sender
):
    """Test subscribing to batches list with userid and filter"""
    # Create handler instance
    handler = Handler(mock_user, mock_websocket_sender, mocker.MagicMock())

    # Create mock data with userid and filter
    data = SubscribeBatchesListData(userid="otheruser", filter="myfilter")

    # Mock the stream_batches_list method to return a coroutine
    mock_stream = mocker.AsyncMock()
    with patch.object(
        handler, "stream_batches_list", return_value=mock_stream
    ) as mock_stream_method:
        # Call subscribe
        await handler.subscribe_batches_list(data)

        # Verify stream was created
        assert handler.batches_list_task is not None
        mock_stream_method.assert_called_once_with("otheruser", "myfilter")


@pytest.mark.asyncio
async def test_unsubscribe_batches_list(mocker, mock_user, mock_websocket_sender):
    """Test unsubscribing from batches list"""
    # Create handler instance
    handler = Handler(mock_user, mock_websocket_sender, mocker.MagicMock())

    # Create a mock task
    mock_task = mocker.MagicMock()
    mock_task.done.return_value = False
    mock_task.cancel = mocker.MagicMock()
    handler.batches_list_task = mock_task

    # Call unsubscribe
    await handler.unsubscribe_batches_list()

    # Verify task was cancelled (but handler still has reference to it)
    mock_task.cancel.assert_called_once()
    # Verify the task is still referenced in the handler
    assert handler.batches_list_task is mock_task


@pytest.mark.asyncio
async def test_subscribe_batch(mocker, mock_user, mock_websocket_sender):
    """Test subscribing to batch items"""
    # Create handler instance
    handler = Handler(mock_user, mock_websocket_sender, mocker.MagicMock())

    # Mock the socket.send_subscribed method
    mock_websocket_sender.send_subscribed = AsyncMock()

    # Call subscribe
    await handler.subscribe_batch(123)

    # Verify stream was created
    assert handler.uploads_task is not None


@pytest.mark.asyncio
async def test_unsubscribe_batch(mocker, mock_user, mock_websocket_sender):
    """Test unsubscribing from batch items"""
    # Create handler instance
    handler = Handler(mock_user, mock_websocket_sender, mocker.MagicMock())

    # Create a mock task
    mock_task = mocker.MagicMock()
    mock_task.done.return_value = False
    mock_task.cancel = mocker.MagicMock()
    handler.uploads_task = mock_task

    # Call unsubscribe
    await handler.unsubscribe_batch()

    # Verify task was cancelled (but handler still has reference to it)
    mock_task.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_stream_batches_list_sends_on_change(
    mocker, mock_user, mock_websocket_sender
):
    """Test that stream_batches_list sends updates when batches change"""
    # Create handler instance
    handler = Handler(mock_user, mock_websocket_sender, mocker.MagicMock())

    with (
        patch("curator.app.handler.Session") as MockSession,
        patch("curator.app.handler.get_batches") as mock_get_batches,
        patch("curator.app.handler.count_batches") as mock_count_batches,
        patch("asyncio.sleep", new_callable=mocker.AsyncMock),
    ):
        session = MockSession.return_value.__enter__.return_value

        # Define items for different states
        stats1 = BatchStats(total=10, completed=5)
        batch1 = BatchItem(
            id=1,
            created_at="2024-01-01T00:00:00",
            username="testuser",
            userid="user123",
            stats=stats1,
        )

        stats2 = BatchStats(total=10, completed=6)
        batch2 = BatchItem(
            id=1,
            created_at="2024-01-01T00:00:00",
            username="testuser",
            userid="user123",
            stats=stats2,
        )

        # Sequence:
        # 1. Initial state (batch1) -> Send
        # 2. No change (batch1) -> No Send
        # 3. Change (batch2) -> Send

        mock_get_batches.side_effect = [
            [batch1],
            [batch1],
            [batch2],
            asyncio.CancelledError,  # Break the loop
        ]

        mock_count_batches.return_value = 1

        # Mock the send_batches_list method
        mock_websocket_sender.send_batches_list = mocker.AsyncMock()

        await handler.stream_batches_list(userid="u1", filter_text="f1")

        # Verify send_batches_list was called twice (once for each change)
        assert mock_websocket_sender.send_batches_list.call_count == 2

        # Verify get_batches was called with correct args
        mock_get_batches.assert_called_with(session, "u1", 0, 100, "f1")

        calls = mock_websocket_sender.send_batches_list.call_args_list
        # First call with batch1
        assert calls[0][0][0].items[0].stats.completed == 5
        # Second call with batch2
        assert calls[1][0][0].items[0].stats.completed == 6

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from curator.app.handler import Handler
from curator.asyncapi import (
    BatchItem,
    BatchStats,
    SubscribeBatchesListData,
)
from curator.protocol import AsyncAPIWebSocket


@pytest.fixture
def mock_sender():
    sender = MagicMock(spec=AsyncAPIWebSocket)
    sender.send_batches_list = AsyncMock()
    return sender


@pytest.fixture
def mock_user():
    return {
        "username": "testuser",
        "userid": "user123",
        "access_token": "token",
    }


@pytest.fixture
def handler_instance(mock_user, mock_sender):
    return Handler(mock_user, mock_sender, MagicMock())


@pytest.mark.asyncio
async def test_subscribe_batches_list(handler_instance):
    # Mock stream_batches_list to return a coroutine
    with patch.object(
        handler_instance, "stream_batches_list", new_callable=AsyncMock
    ) as mock_stream:
        data = SubscribeBatchesListData()
        await handler_instance.subscribe_batches_list(data)

        # Check if task is created
        assert handler_instance.batches_list_task is not None
        mock_stream.assert_called_once_with(None, None)


@pytest.mark.asyncio
async def test_subscribe_batches_list_with_args(handler_instance):
    # Mock stream_batches_list to return a coroutine
    with patch.object(
        handler_instance, "stream_batches_list", new_callable=AsyncMock
    ) as mock_stream:
        data = SubscribeBatchesListData(userid="otheruser", filter="myfilter")
        await handler_instance.subscribe_batches_list(data)

        # Check if task is created
        assert handler_instance.batches_list_task is not None
        mock_stream.assert_called_once_with("otheruser", "myfilter")


@pytest.mark.asyncio
async def test_unsubscribe_batches_list(handler_instance):
    # Create a dummy task
    handler_instance.batches_list_task = asyncio.create_task(asyncio.sleep(1))

    await handler_instance.unsubscribe_batches_list()

    await asyncio.sleep(0)
    assert handler_instance.batches_list_task.cancelled()


@pytest.mark.asyncio
async def test_stream_batches_list_sends_on_change(handler_instance, mock_sender):
    with (
        patch("curator.app.handler.Session") as MockSession,
        patch("curator.app.handler.get_batches") as mock_get_batches,
        patch("curator.app.handler.count_batches") as mock_count_batches,
        patch("asyncio.sleep", new_callable=AsyncMock),
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

        await handler_instance.stream_batches_list(userid="u1", filter_text="f1")
        assert mock_sender.send_batches_list.call_count == 2

        # Verify get_batches was called with correct args
        mock_get_batches.assert_called_with(session, "u1", 0, 100, "f1")

        calls = mock_sender.send_batches_list.call_args_list
        # First call with batch1
        assert calls[0][0][0].items[0].stats.completed == 5
        # Second call with batch2
        assert calls[1][0][0].items[0].stats.completed == 6

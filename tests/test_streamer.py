"""Tests for WebSocket streaming functionality."""

import asyncio
from datetime import datetime
from unittest.mock import patch

import pytest

from curator.app.handler_optimized import OptimizedBatchStreamer
from curator.asyncapi import BatchItem, BatchStats


@pytest.fixture(autouse=True)
def patch_streamer_get_session(patch_get_session):
    return patch_get_session("curator.app.handler_optimized.get_session")


@pytest.mark.asyncio
async def test_streamer_full_sync_initially(mock_sender):
    streamer = OptimizedBatchStreamer(mock_sender, "testuser")

    with (
        patch(
            "curator.app.handler_optimized.get_batches_optimized"
        ) as mock_get_batches,
        patch(
            "curator.app.handler_optimized.count_batches_optimized"
        ) as mock_count_batches,
        patch("curator.app.handler_optimized.get_latest_update_time") as mock_latest,
        patch("asyncio.sleep", side_effect=asyncio.CancelledError),
    ):
        mock_get_batches.return_value = [
            BatchItem(
                id=1,
                created_at=datetime.now().isoformat(),
                username="u1",
                userid="u1",
                stats=BatchStats(),
            )
        ]
        mock_count_batches.return_value = 1
        mock_latest.return_value = datetime.now()

        try:
            await streamer.start_streaming(userid="u1")
        except asyncio.CancelledError:
            pass

        # Should have sent a full sync (partial=False)
        mock_sender.send_batches_list.assert_called_once()
        args, kwargs = mock_sender.send_batches_list.call_args
        assert kwargs["partial"] is False
        assert len(args[0].items) == 1


@pytest.mark.asyncio
async def test_streamer_incremental_update(mock_sender):
    streamer = OptimizedBatchStreamer(mock_sender, "testuser")

    t1 = datetime(2023, 1, 1, 12, 0, 0)
    t2 = datetime(2023, 1, 1, 12, 0, 5)

    with (
        patch("curator.app.handler_optimized.get_batches_optimized") as mock_full,
        patch("curator.app.handler_optimized.get_batches_minimal") as mock_mini,
        patch(
            "curator.app.handler_optimized.get_batch_ids_with_recent_changes"
        ) as mock_changed,
        patch("curator.app.handler_optimized.get_latest_update_time") as mock_latest,
        patch("curator.app.handler_optimized.count_batches_optimized") as mock_count,
        patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]),
    ):
        # Initial sync
        mock_latest.side_effect = [t1, t2]  # t1 for init, t2 for loop check
        mock_full.return_value = []
        mock_count.return_value = 0

        # Incremental
        mock_changed.return_value = [1]
        mock_mini.return_value = [
            BatchItem(
                id=1,
                created_at=t1.isoformat(),
                username="u1",
                userid="u1",
                stats=BatchStats(total=1, completed=1),
            )
        ]

        try:
            await streamer.start_streaming(userid="u1")
        except asyncio.CancelledError:
            pass

        # Should have called send_batches_list twice: once full, once partial
        assert mock_sender.send_batches_list.call_count == 2

        # Second call should be partial
        args, kwargs = mock_sender.send_batches_list.call_args
        assert kwargs["partial"] is True
        assert args[0].items[0].id == 1


@pytest.mark.asyncio
async def test_streamer_no_update_if_time_same(mock_sender):
    streamer = OptimizedBatchStreamer(mock_sender, "testuser")
    t1 = datetime(2023, 1, 1, 12, 0, 0)

    with (
        patch("curator.app.handler_optimized.get_batches_optimized") as mock_full,
        patch("curator.app.handler_optimized.get_latest_update_time") as mock_latest,
        patch("curator.app.handler_optimized.count_batches_optimized") as mock_count,
        patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]),
    ):
        # Time doesn't change
        mock_latest.return_value = t1
        mock_full.return_value = []
        mock_count.return_value = 0

        try:
            await streamer.start_streaming()
        except asyncio.CancelledError:
            pass

        # Only initial sync should be called
        assert mock_sender.send_batches_list.call_count == 1
        _, kwargs = mock_sender.send_batches_list.call_args
        assert kwargs["partial"] is False


@pytest.mark.asyncio
async def test_streamer_no_updates_on_paginated_page(mock_sender):
    streamer = OptimizedBatchStreamer(mock_sender, "testuser")
    t1 = datetime(2023, 1, 1, 12, 0, 0)

    with (
        patch("curator.app.handler_optimized.get_batches_optimized") as mock_full,
        patch("curator.app.handler_optimized.get_latest_update_time") as mock_latest,
        patch("curator.app.handler_optimized.count_batches_optimized") as mock_count,
        patch("asyncio.sleep") as mock_sleep,
    ):
        mock_latest.return_value = t1
        mock_full.return_value = []
        mock_count.return_value = 0

        # Start streaming for page 2
        await streamer.start_streaming(page=2)

        # Should have sent a full sync (partial=False)
        mock_sender.send_batches_list.assert_called_once()
        _, kwargs = mock_sender.send_batches_list.call_args
        assert kwargs["partial"] is False

        # asyncio.sleep should NOT have been called (the loop was bypassed)
        mock_sleep.assert_not_called()

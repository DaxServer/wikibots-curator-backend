"""Tests for WebSocket handler operations."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from curator.asyncapi import RetryUploads


@pytest.mark.asyncio
async def test_handle_subscribe_batch(handler_instance, mock_sender):
    # Mock stream_uploads to return a coroutine
    mock_stream = AsyncMock()

    with patch.object(handler_instance, "stream_uploads", side_effect=mock_stream):
        await handler_instance.subscribe_batch(123)

        mock_sender.send_subscribed.assert_called_once_with(123)
        assert handler_instance.uploads_task is not None


@pytest.mark.asyncio
async def test_handle_unsubscribe_batch(handler_instance):
    # Create a dummy task
    handler_instance.uploads_task = asyncio.create_task(asyncio.sleep(1))

    await handler_instance.unsubscribe_batch()

    await asyncio.sleep(0)
    assert handler_instance.uploads_task.cancelled()


@pytest.mark.asyncio
async def test_retry_uploads_success(mocker, handler_instance):
    with (
        patch("curator.core.handler.reset_failed_uploads_to_new_batch") as mock_reset,
        patch("curator.core.task_enqueuer.process_upload") as mock_process_upload,
        patch(
            "curator.core.task_enqueuer.get_rate_limit_for_batch"
        ) as mock_get_rate_limit,
        patch("curator.core.task_enqueuer.get_next_upload_delay") as mock_get_delay,
        patch("curator.core.task_enqueuer.register_user_queue"),
    ):
        mock_reset.return_value = ([1, 2], "newbatch123", 456)
        mock_get_rate_limit.return_value = mocker.MagicMock()
        mock_get_delay.return_value = 0.0

        await handler_instance.retry_uploads(123)

        mock_reset.assert_called_once()
        assert mock_process_upload.apply_async.call_count == 2
        for call in mock_process_upload.apply_async.call_args_list:
            assert call[1]["queue"] == "uploads-user123"
            assert call[1]["args"][1] == "newbatch123"


@pytest.mark.asyncio
async def test_retry_uploads_no_failures(handler_instance, mock_sender):
    with (
        patch("curator.core.handler.reset_failed_uploads_to_new_batch") as mock_reset,
        patch("curator.core.task_enqueuer.process_upload") as mock_process_upload,
    ):
        mock_reset.return_value = ([], None, 0)

        data = RetryUploads(data=123)
        await handler_instance.retry_uploads(data.data)

        mock_reset.assert_called_once()
        mock_process_upload.apply_async.assert_not_called()  # Should not be called when no failures
        mock_sender.send_error.assert_called_once_with("No failed uploads to retry")


@pytest.mark.asyncio
async def test_retry_uploads_forbidden(handler_instance, mock_sender):
    with (
        patch("curator.core.handler.reset_failed_uploads_to_new_batch") as mock_reset,
        patch("curator.core.task_enqueuer.process_upload") as mock_process_upload,
    ):
        mock_reset.side_effect = PermissionError("Permission denied")

        data = RetryUploads(data=123)
        await handler_instance.retry_uploads(data.data)

        mock_reset.assert_called_once()
        mock_process_upload.apply_async.assert_not_called()  # Should not be called when error occurs
        mock_sender.send_error.assert_called_once_with("Permission denied")


@pytest.mark.asyncio
async def test_retry_uploads_not_found(handler_instance, mock_sender):
    with (
        patch("curator.core.handler.reset_failed_uploads_to_new_batch") as mock_reset,
        patch("curator.core.task_enqueuer.process_upload") as mock_process_upload,
    ):
        mock_reset.side_effect = ValueError("Batch not found")

        data = RetryUploads(data=123)
        await handler_instance.retry_uploads(data.data)

        mock_reset.assert_called_once()
        mock_process_upload.apply_async.assert_not_called()  # Should not be called when error occurs
        mock_sender.send_error.assert_called_once_with("Batch 123 not found")


@pytest.mark.asyncio
async def test_retry_uploads_enqueues_with_edit_group_id(mocker, handler_instance):
    """Test retry uploads enqueues with correct upload_ids and edit_group_id"""
    with (
        patch("curator.core.handler.reset_failed_uploads_to_new_batch") as mock_reset,
        patch("curator.core.task_enqueuer.process_upload") as mock_process_upload,
        patch(
            "curator.core.task_enqueuer.get_rate_limit_for_batch"
        ) as mock_get_rate_limit,
        patch("curator.core.task_enqueuer.get_next_upload_delay") as mock_get_delay,
        patch("curator.core.task_enqueuer.register_user_queue"),
    ):
        mock_reset.return_value = ([1, 2], "newbatch456", 789)
        mock_get_rate_limit.return_value = mocker.MagicMock()
        mock_get_delay.return_value = 0.0

        await handler_instance.retry_uploads(123)

        assert mock_process_upload.apply_async.call_count == 2
        calls = mock_process_upload.apply_async.call_args_list
        upload_ids = {call[1]["args"][0] for call in calls}
        assert upload_ids == {1, 2}
        for call in calls:
            assert len(call[1]["args"]) == 3
            assert call[1]["args"][1] == "newbatch456"
            assert call[1]["args"][2] == "user123"
            assert call[1]["queue"] == "uploads-user123"

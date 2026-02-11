import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from curator.app.config import QueuePriority
from curator.asyncapi import (
    BatchItem,
    BatchStats,
    BatchUploadItem,
    FetchBatchesData,
    RetryUploads,
)
from curator.workers.celery import QUEUE_NORMAL, QUEUE_PRIVILEGED


@pytest.fixture(autouse=True)
def mock_isolated_site(mocker):
    """Mock create_isolated_site to return a mock site for Handler._get_site()"""
    mock_site = MagicMock()
    mock_site.has_group = MagicMock(return_value=True)  # Default to privileged
    return mocker.patch(
        "curator.app.commons.create_isolated_site", return_value=mock_site
    )


@pytest.mark.asyncio
async def test_handle_fetch_images_success(handler_instance, mock_sender, mock_image):
    from curator.asyncapi import ImageHandler

    with patch("curator.app.handler.get_handler_for_handler_type") as mock_get_handler:
        mock_handler = MagicMock()
        mock_handler.fetch_collection = AsyncMock(return_value={"img1": mock_image})
        mock_handler.fetch_existing_pages.return_value = {"img1": []}
        mock_handler.name = "mapillary"
        mock_get_handler.return_value = mock_handler

        await handler_instance.fetch_images("some_input", ImageHandler.MAPILLARY)

        assert mock_sender.send_collection_images.call_count == 1
        call_args = mock_sender.send_collection_images.call_args[0][0]
        assert call_args.creator.username == mock_image.creator.username
        assert len(call_args.images) == 1


@pytest.mark.asyncio
async def test_handle_fetch_images_not_found(handler_instance, mock_sender):
    from curator.asyncapi import ImageHandler

    with patch("curator.app.handler.get_handler_for_handler_type") as mock_get_handler:
        mock_handler = MagicMock()
        mock_handler.fetch_collection = AsyncMock(return_value={})
        mock_handler.name = "mapillary"
        mock_get_handler.return_value = mock_handler

        await handler_instance.fetch_images("invalid", ImageHandler.MAPILLARY)

        mock_sender.send_error.assert_called_once_with("Collection not found")


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
async def test_stream_uploads(mocker, handler_instance, mock_sender):
    with (
        patch("curator.app.handler.get_upload_request") as mock_get,
        patch("curator.app.handler.count_uploads_in_batch") as mock_count,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_req = mocker.MagicMock()
        mock_req.id = 1
        mock_req.status = "completed"
        mock_req.key = "img1"
        mock_req.batchid = 123
        mock_req.error = None
        mock_req.success = "http://example.com/img1.jpg"
        mock_req.handler = "mapillary"

        mock_get.return_value = [mock_req]
        mock_count.return_value = 1

        await handler_instance.stream_uploads(123)

        mock_sender.send_uploads_update.assert_called_once()
        mock_sender.send_uploads_complete.assert_called_once_with(123)


@pytest.mark.asyncio
async def test_handle_fetch_batches(handler_instance, mock_sender):
    with patch("curator.app.handler.OptimizedBatchStreamer") as MockStreamer:
        mock_streamer_instance = MockStreamer.return_value
        mock_streamer_instance.start_streaming = AsyncMock()

        # Mock send_subscribed
        data = FetchBatchesData(page=1, limit=100, userid="user123", filter="test")
        await handler_instance.fetch_batches(data)

        # 1. Should start streaming with correct params on the NEW instance
        mock_streamer_instance.start_streaming.assert_called_once_with(
            "user123", "test", page=1, limit=100
        )

        # 2. Should store the task
        assert handler_instance.batches_list_task is not None


@pytest.mark.asyncio
async def test_handle_fetch_batch_uploads(handler_instance, mock_sender):
    with (
        patch("curator.app.handler.get_batch") as mock_get_batch,
        patch("curator.app.handler.get_upload_request") as mock_get_uploads,
        patch("curator.app.handler.count_uploads_in_batch") as mock_count_uploads,
    ):
        batch = BatchItem(
            id=1,
            created_at="2024-01-01T00:00:00",
            username="testuser",
            userid="user123",
            stats=BatchStats(),
        )

        upload = BatchUploadItem(
            id=1,
            status="completed",
            filename="test.jpg",
            wikitext="wikitext",
            batchid=1,
            key="img1",
            image_id="img1",
            error=None,
            success=None,
            handler="mapillary",
        )

        mock_get_batch.return_value = batch
        mock_get_uploads.return_value = [upload]
        mock_count_uploads.return_value = 1

        await handler_instance.fetch_batch_uploads(1)

        mock_sender.send_batch_uploads_list.assert_called_once()
        call_args = mock_sender.send_batch_uploads_list.call_args[0][0]
        # call_args is BatchUploadsListData
        assert call_args.batch.id == 1
        assert len(call_args.uploads) == 1
        assert call_args.uploads[0].id == 1


@pytest.mark.asyncio
async def test_handle_fetch_images_api_error(mocker, handler_instance, mock_sender):
    from curator.asyncapi import ImageHandler

    with patch("curator.app.handler.get_handler_for_handler_type") as mock_get_handler:
        mock_handler = mocker.MagicMock()
        mock_handler.fetch_collection = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Error message",
                request=mocker.MagicMock(),
                response=mocker.MagicMock(status_code=502, text="502 error"),
            )
        )
        mock_handler.name = "mapillary"
        mock_get_handler.return_value = mock_handler

        await handler_instance.fetch_images(
            "invalid_collection", ImageHandler.MAPILLARY
        )

        mock_sender.send_error.assert_called_once()
        args = mock_sender.send_error.call_args[0]
        assert "Mapillary API Error" in args[0]
        assert "502 error" in args[0]


@pytest.mark.asyncio
async def test_stream_uploads_only_sends_on_change(
    mocker, handler_instance, mock_sender
):
    with (
        patch("curator.app.handler.get_upload_request") as mock_get,
        patch("curator.app.handler.count_uploads_in_batch") as mock_count,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        # Define items for different states
        # 1. Initial state
        item_v1 = mocker.MagicMock()
        item_v1.id = 1
        item_v1.status = "queued"
        item_v1.key = "img1"
        item_v1.handler = "mapillary"
        item_v1.error = None
        item_v1.success = None

        # 2. Changed state
        item_v2 = mocker.MagicMock()
        item_v2.id = 1
        item_v2.status = "in_progress"
        item_v2.key = "img1"
        item_v2.handler = "mapillary"
        item_v2.error = None
        item_v2.success = None

        # 3. Completed state
        item_v3 = mocker.MagicMock()
        item_v3.id = 1
        item_v3.status = "completed"
        item_v3.key = "img1"
        item_v3.handler = "mapillary"
        item_v3.error = None
        item_v3.success = None

        # Sequence of returns:
        # 1. v1 -> should send
        # 2. v1 -> should NOT send
        # 3. v2 -> should send
        # 4. v2 -> should NOT send
        # 5. v3 -> should send and finish

        mock_get.side_effect = [
            [item_v1],
            [item_v1],
            [item_v2],
            [item_v2],
            [item_v3],
        ]

        # count_uploads_in_batch is called after sending.
        # We need it to NOT complete for the first 4 calls, and complete on the 5th.
        mock_count.return_value = 1

        await handler_instance.stream_uploads(123)

        # We WANT it to be 3 (v1, v2, v3).
        assert mock_sender.send_uploads_update.call_count == 3

        # Let's also verify the arguments to be sure
        calls = mock_sender.send_uploads_update.call_args_list
        assert calls[0][0][0][0].status == "queued"
        assert calls[1][0][0][0].status == "in_progress"
        assert calls[2][0][0][0].status == "completed"


@pytest.mark.asyncio
async def test_retry_uploads_success(mocker, handler_instance):
    with (
        patch("curator.app.handler.reset_failed_uploads") as mock_reset,
        patch("curator.app.handler.process_upload") as mock_process_upload,
        patch("curator.app.handler.get_rate_limit_for_batch") as mock_get_rate_limit,
    ):
        mock_reset.return_value = [1, 2]
        mock_get_rate_limit.return_value = mocker.MagicMock(is_privileged=False)
        await handler_instance.retry_uploads(123)

        mock_reset.assert_called_once()
        assert mock_process_upload.apply_async.call_count == 2
        # Check that calls were made with queue parameter
        for call in mock_process_upload.apply_async.call_args_list:
            assert call[1]["queue"] in [QUEUE_PRIVILEGED, QUEUE_NORMAL]


@pytest.mark.asyncio
async def test_handle_fetch_batch_uploads_exception(handler_instance, mock_sender):
    with (
        patch("curator.app.handler.get_batch") as mock_get_batch,
        patch("curator.app.handler.logger") as mock_logger,
    ):
        mock_get_batch.side_effect = Exception("DB Error")

        await handler_instance.fetch_batch_uploads(1)

        mock_logger.exception.assert_called_once()
        mock_sender.send_error.assert_called_once_with(
            "Internal server error.. please notify User:DaxServer"
        )


@pytest.mark.asyncio
async def test_retry_uploads_no_failures(handler_instance, mock_sender):
    with (
        patch("curator.app.handler.reset_failed_uploads") as mock_reset,
        patch("curator.app.handler.process_upload") as mock_process_upload,
    ):
        mock_reset.return_value = []

        data = RetryUploads(data=123)
        await handler_instance.retry_uploads(data.data)

        mock_reset.assert_called_once()
        mock_process_upload.apply_async.assert_not_called()  # Should not be called when no failures
        mock_sender.send_error.assert_called_once_with("No failed uploads to retry")


@pytest.mark.asyncio
async def test_retry_uploads_forbidden(handler_instance, mock_sender):
    with (
        patch("curator.app.handler.reset_failed_uploads") as mock_reset,
        patch("curator.app.handler.process_upload") as mock_process_upload,
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
        patch("curator.app.handler.reset_failed_uploads") as mock_reset,
        patch("curator.app.handler.process_upload") as mock_process_upload,
    ):
        mock_reset.side_effect = ValueError("Batch not found")

        data = RetryUploads(data=123)
        await handler_instance.retry_uploads(data.data)

        mock_reset.assert_called_once()
        mock_process_upload.apply_async.assert_not_called()  # Should not be called when error occurs
        mock_sender.send_error.assert_called_once_with("Batch 123 not found")


@pytest.mark.asyncio
@pytest.mark.parametrize("priority", [None, QueuePriority.URGENT, QueuePriority.LATER])
async def test_retry_uploads_with_priority(mocker, handler_instance, priority):
    """Test retry uploads with different priorities"""
    with (
        patch("curator.app.handler.reset_failed_uploads") as mock_reset,
        patch("curator.app.handler.process_upload") as mock_process_upload,
        patch("curator.app.handler.get_rate_limit_for_batch") as mock_get_rate_limit,
    ):
        mock_reset.return_value = [1, 2]
        mock_get_rate_limit.return_value = mocker.MagicMock(is_privileged=False)

        if priority:
            await handler_instance.retry_uploads(123, priority=priority)
        else:
            await handler_instance.retry_uploads(123)

        assert mock_process_upload.apply_async.call_count == 2
        # Check that calls were made with upload_id, edit_group_id, and queue
        calls = mock_process_upload.apply_async.call_args_list
        upload_ids = {call[1]["args"][0] for call in calls}
        assert upload_ids == {1, 2}
        # Verify all calls have edit_group_id and queue
        for call in calls:
            assert len(call[1]["args"]) == 2
            assert isinstance(call[1]["args"][1], str)
            assert len(call[1]["args"][1]) == 12
            assert call[1]["queue"] in [QUEUE_PRIVILEGED, QUEUE_NORMAL]

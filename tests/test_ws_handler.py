import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from curator.app.handler import Handler
from curator.asyncapi import (
    BatchItem,
    BatchStats,
    BatchUploadItem,
    Creator,
    Dates,
    FetchBatchesData,
    GeoLocation,
    MediaImage,
    RetryUploads,
    UploadData,
    UploadItem,
)
from curator.protocol import AsyncAPIWebSocket
from curator.workers.rq import QueuePriority


@pytest.fixture
def mock_sender(mocker):
    sender = mocker.MagicMock(spec=AsyncAPIWebSocket)
    sender.send_collection_images = AsyncMock()
    sender.send_error = AsyncMock()
    sender.send_upload_created = AsyncMock()
    sender.send_subscribed = AsyncMock()
    sender.send_uploads_update = AsyncMock()
    sender.send_uploads_complete = AsyncMock()
    sender.send_batches_list = AsyncMock()
    sender.send_batch_uploads_list = AsyncMock()
    return sender


@pytest.fixture
def handler_instance(mocker, mock_user, mock_sender, mock_session):
    return Handler(mock_user, mock_sender, mocker.MagicMock())


@pytest.mark.asyncio
async def test_handle_fetch_images_success(handler_instance, mock_sender):
    with patch("curator.app.handler.MapillaryHandler") as MockHandler:
        handler = MockHandler.return_value

        image = MediaImage(
            id="img1",
            title="Image 1",
            url_original="http://original",
            thumbnail_url="http://thumb",
            preview_url="http://preview",
            url="http://url",
            width=100,
            height=100,
            description="desc",
            camera_make="Canon",
            camera_model="EOS",
            is_pano=False,
            license="CC",
            tags=["tag1"],
            location=GeoLocation(latitude=1.0, longitude=2.0, compass_angle=0),
            existing=[],
            creator=Creator(id="c1", username="creator1", profile_url="http://profile"),
            dates=Dates(taken="2023-01-01"),
        )

        handler.fetch_collection = AsyncMock(return_value={"img1": image})
        handler.fetch_existing_pages.return_value = {"img1": []}

        await handler_instance.fetch_images("some_input")

        assert mock_sender.send_collection_images.call_count == 1
        call_args = mock_sender.send_collection_images.call_args[0][0]
        # call_args is CollectionImagesData
        assert call_args.creator.username == "creator1"
        assert len(call_args.images) == 1
        assert call_args.images["img1"].id == "img1"


@pytest.mark.asyncio
async def test_handle_fetch_images_not_found(handler_instance, mock_sender):
    with patch("curator.app.handler.MapillaryHandler") as MockHandler:
        handler = MockHandler.return_value
        handler.fetch_collection = AsyncMock(return_value={})

        await handler_instance.fetch_images("invalid")

        mock_sender.send_error.assert_called_once_with("Collection not found")


@pytest.mark.asyncio
async def test_handle_upload(mocker, mock_user, mock_sender, mock_session):
    with (
        patch("curator.app.handler.get_session", return_value=iter([mock_session])),
        patch("curator.app.handler.create_upload_request") as mock_create,
        patch("curator.app.handler.get_queue") as mock_get_queue,
    ):
        handler_instance = Handler(mock_user, mock_sender, mocker.MagicMock())

        mock_req = mocker.MagicMock()
        mock_req.id = 1
        mock_req.status = "pending"
        mock_req.key = "img1"
        mock_req.batchid = 100
        mock_req._sa_instance_state = mocker.MagicMock()
        mock_req._sa_instance_state.class_.__name__ = "UploadRequest"

        mock_create.return_value = [mock_req]

        data = UploadData(
            items=[
                UploadItem(
                    input="test",
                    id="1",
                    title="Test Title",
                    wikitext="Test Wikitext",
                )
            ],
            handler="mapillary",
        )

        await handler_instance.upload(data)

        mock_get_queue.assert_called_once_with(QueuePriority.NORMAL)
        mock_queue = mock_get_queue.return_value
        mock_queue.enqueue_many.assert_called_once()
        mock_sender.send_upload_created.assert_called_once()
        call_args = mock_sender.send_upload_created.call_args[0][0]
        # call_args is List[UploadCreatedItem]
        assert call_args[0].id == 1


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
    with patch("curator.app.handler.MapillaryHandler") as MockHandler:
        handler = MockHandler.return_value

        # Create a mock response with a text property
        mock_response = mocker.MagicMock()
        mock_response.status_code = 500
        mock_response.text = "500 error"

        # Raise HTTPStatusError
        error = httpx.HTTPStatusError(
            "Error message", request=mocker.MagicMock(), response=mock_response
        )
        handler.fetch_collection = AsyncMock(side_effect=error)

        await handler_instance.fetch_images("invalid_collection")

        # The handler should send the error message which includes response.text
        mock_sender.send_error.assert_called_once()
        args = mock_sender.send_error.call_args[0]
        assert "Mapillary API Error" in args[0]
        assert "500 error" in args[0]


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
async def test_retry_uploads_success(handler_instance):
    with (
        patch("curator.app.handler.reset_failed_uploads") as mock_reset,
        patch("curator.app.handler.get_queue") as mock_get_queue,
    ):
        mock_reset.return_value = [1, 2]

        data = RetryUploads(data=123)
        await handler_instance.retry_uploads(data.data)

        mock_reset.assert_called_once()
        mock_get_queue.assert_called_once_with(QueuePriority.NORMAL)
        mock_queue = mock_get_queue.return_value
        mock_queue.enqueue_many.assert_called_once()


@pytest.mark.asyncio
async def test_retry_uploads_no_failures(handler_instance, mock_sender):
    with (
        patch("curator.app.handler.reset_failed_uploads") as mock_reset,
        patch("curator.app.handler.get_queue") as mock_get_queue,
    ):
        mock_reset.return_value = []

        data = RetryUploads(data=123)
        await handler_instance.retry_uploads(data.data)

        mock_reset.assert_called_once()
        mock_get_queue.assert_not_called()  # Should not be called when no failures
        mock_sender.send_error.assert_called_once_with("No failed uploads to retry")


@pytest.mark.asyncio
async def test_retry_uploads_forbidden(handler_instance, mock_sender):
    with (
        patch("curator.app.handler.reset_failed_uploads") as mock_reset,
        patch("curator.app.handler.get_queue") as mock_get_queue,
    ):
        mock_reset.side_effect = PermissionError("Permission denied")

        data = RetryUploads(data=123)
        await handler_instance.retry_uploads(data.data)

        mock_reset.assert_called_once()
        mock_get_queue.assert_not_called()  # Should not be called when error occurs
        mock_sender.send_error.assert_called_once_with("Permission denied")


@pytest.mark.asyncio
async def test_retry_uploads_not_found(handler_instance, mock_sender):
    with (
        patch("curator.app.handler.reset_failed_uploads") as mock_reset,
        patch("curator.app.handler.get_queue") as mock_get_queue,
    ):
        mock_reset.side_effect = ValueError("Batch not found")

        data = RetryUploads(data=123)
        await handler_instance.retry_uploads(data.data)

        mock_reset.assert_called_once()
        mock_get_queue.assert_not_called()  # Should not be called when error occurs
        mock_sender.send_error.assert_called_once_with("Batch 123 not found")


# Priority Queue Tests
@pytest.mark.asyncio
async def test_upload_with_priority_urgent(
    mocker, mock_user, mock_sender, mock_session
):
    """Test upload with URGENT priority"""
    with (
        patch("curator.app.handler.get_session", return_value=iter([mock_session])),
        patch("curator.app.handler.create_upload_request") as mock_create,
        patch("curator.app.handler.get_queue") as mock_get_queue,
    ):
        handler_instance = Handler(mock_user, mock_sender, mocker.MagicMock())

        mock_queue = mock_get_queue.return_value

        mock_req = mocker.MagicMock()
        mock_req.id = 1
        mock_req.status = "pending"
        mock_req.key = "img1"
        mock_req.batchid = 100
        mock_req._sa_instance_state = mocker.MagicMock()
        mock_req._sa_instance_state.class_.__name__ = "UploadRequest"

        mock_create.return_value = [mock_req]

        data = UploadData(
            items=[
                UploadItem(
                    input="test",
                    id="1",
                    title="Test Title",
                    wikitext="Test Wikitext",
                )
            ],
            handler="mapillary",
        )

        await handler_instance.upload(data, priority=QueuePriority.URGENT)

        # Verify get_queue was called with URGENT priority
        mock_get_queue.assert_called_once_with(QueuePriority.URGENT)
        mock_queue.enqueue_many.assert_called_once()
        mock_sender.send_upload_created.assert_called_once()


@pytest.mark.asyncio
async def test_upload_with_priority_later(mocker, mock_user, mock_sender, mock_session):
    """Test upload with LATER priority"""
    with (
        patch("curator.app.handler.get_session", return_value=iter([mock_session])),
        patch("curator.app.handler.create_upload_request") as mock_create,
        patch("curator.app.handler.get_queue") as mock_get_queue,
    ):
        handler_instance = Handler(mock_user, mock_sender, mocker.MagicMock())

        mock_queue = mock_get_queue.return_value

        mock_req = mocker.MagicMock()
        mock_req.id = 1
        mock_req.status = "pending"
        mock_req.key = "img1"
        mock_req.batchid = 100
        mock_req._sa_instance_state = mocker.MagicMock()
        mock_req._sa_instance_state.class_.__name__ = "UploadRequest"

        mock_create.return_value = [mock_req]

        data = UploadData(
            items=[
                UploadItem(
                    input="test",
                    id="1",
                    title="Test Title",
                    wikitext="Test Wikitext",
                )
            ],
            handler="mapillary",
        )

        await handler_instance.upload(data, priority=QueuePriority.LATER)

        # Verify get_queue was called with LATER priority
        mock_get_queue.assert_called_once_with(QueuePriority.LATER)
        mock_queue.enqueue_many.assert_called_once()
        mock_sender.send_upload_created.assert_called_once()


@pytest.mark.asyncio
async def test_retry_uploads_with_priority_urgent(handler_instance):
    """Test retry uploads with URGENT priority"""
    with (
        patch("curator.app.handler.reset_failed_uploads") as mock_reset,
        patch("curator.app.handler.get_queue") as mock_get_queue,
    ):
        mock_queue = mock_get_queue.return_value
        mock_reset.return_value = [1, 2]

        data = RetryUploads(data=123)
        await handler_instance.retry_uploads(data.data, priority=QueuePriority.URGENT)

        # Verify get_queue was called with URGENT priority
        mock_get_queue.assert_called_once_with(QueuePriority.URGENT)
        mock_queue.enqueue_many.assert_called_once()


@pytest.mark.asyncio
async def test_retry_uploads_with_priority_later(handler_instance):
    """Test retry uploads with LATER priority"""
    with (
        patch("curator.app.handler.reset_failed_uploads") as mock_reset,
        patch("curator.app.handler.get_queue") as mock_get_queue,
    ):
        mock_queue = mock_get_queue.return_value
        mock_reset.return_value = [1, 2]

        data = RetryUploads(data=123)
        await handler_instance.retry_uploads(data.data, priority=QueuePriority.LATER)

        # Verify get_queue was called with LATER priority
        mock_get_queue.assert_called_once_with(QueuePriority.LATER)
        mock_queue.enqueue_many.assert_called_once()

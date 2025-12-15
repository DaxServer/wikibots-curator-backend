from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from curator.app.handler import Handler
from curator.app.models import UploadItem
from curator.asyncapi import (
    BatchItem,
    BatchStats,
    BatchUploadItem,
    Creator,
    Dates,
    FetchBatchesData,
    FetchBatchUploadsData,
    Image,
    UploadData,
)
from curator.protocol import AsyncAPIWebSocket


@pytest.fixture
def mock_sender():
    sender = MagicMock(spec=AsyncAPIWebSocket)
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
async def test_handle_fetch_images_success(handler_instance, mock_sender):
    with patch("curator.app.handler.MapillaryHandler") as MockHandler:
        handler = MockHandler.return_value

        # Create real objects
        creator = Creator(id="c1", username="creator1", profile_url="http://profile")
        dates = Dates(taken="2023-01-01", published="2023-01-02")
        image = Image(
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
            location=None,
            existing=[],
            creator=creator,
            dates=dates,
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
async def test_handle_upload(handler_instance, mock_sender):
    with (
        patch("curator.app.handler.Session") as MockSession,
        patch("curator.app.handler.create_upload_request") as mock_create,
        patch("curator.app.handler.ingest_queue") as mock_worker,
    ):

        session = MockSession.return_value.__enter__.return_value

        mock_req = MagicMock()
        mock_req.id = 1
        mock_req.status = "pending"
        mock_req.key = "img1"
        mock_req.batchid = 100

        mock_create.return_value = [mock_req]

        data = UploadData(
            items=[
                UploadItem(
                    input="test",
                    id="img1",
                    title="Test Title",
                    wikitext="Test Wikitext",
                )
            ],
            handler="mapillary",
        )

        await handler_instance.upload(data)

        mock_worker.enqueue_many.assert_called_once()
        mock_sender.send_upload_created.assert_called_once()
        call_args = mock_sender.send_upload_created.call_args[0][0]
        # call_args is List[UploadCreatedItem]
        assert call_args[0].id == 1


@pytest.mark.asyncio
async def test_handle_subscribe_batch(handler_instance, mock_sender):
    # Mock stream_uploads to return a coroutine
    mock_stream = AsyncMock()

    with patch.object(
        handler_instance, "stream_uploads", side_effect=mock_stream
    ) as mock_method:
        await handler_instance.subscribe_batch(123)

        mock_sender.send_subscribed.assert_called_once_with(123)
        assert handler_instance.uploads_task is not None


@pytest.mark.asyncio
async def test_stream_uploads(handler_instance, mock_sender):
    with (
        patch("curator.app.handler.Session") as MockSession,
        patch("curator.app.handler.get_upload_request") as mock_get,
        patch("curator.app.handler.count_uploads_in_batch") as mock_count,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):

        session = MockSession.return_value.__enter__.return_value

        mock_req = MagicMock()
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
    with (
        patch("curator.app.handler.Session") as MockSession,
        patch("curator.app.handler.get_batches") as mock_get_batches,
        patch("curator.app.handler.count_batches") as mock_count_batches,
    ):
        session = MockSession.return_value.__enter__.return_value

        stats = BatchStats(
            total=10,
            queued=2,
            in_progress=3,
            completed=4,
            failed=1,
        )
        batch = BatchItem(
            id=1,
            created_at="2024-01-01T00:00:00",
            username="testuser",
            userid="user123",
            stats=stats,
        )

        mock_get_batches.return_value = [batch]
        mock_count_batches.return_value = 1

        await handler_instance.fetch_batches(FetchBatchesData())

        mock_sender.send_batches_list.assert_called_once()
        call_args = mock_sender.send_batches_list.call_args[0][0]
        # call_args is BatchesListData
        assert len(call_args.items) == 1
        item = call_args.items[0]
        # item is BatchItem
        assert item.id == 1
        assert item.stats.total == 10
        assert item.stats.completed == 4
        assert item.stats.failed == 1
        assert item.stats.queued == 2
        assert item.stats.in_progress == 3
        assert item.stats.duplicate == 0
        assert call_args.total == 1

        # Verify defaults were used (page=1, limit=100 -> offset=0)
        mock_get_batches.assert_called_with(session, None, 0, 100)


@pytest.mark.asyncio
async def test_handle_fetch_batch_uploads(handler_instance, mock_sender):
    with (
        patch("curator.app.handler.Session") as MockSession,
        patch("curator.app.handler.get_upload_request") as mock_get_uploads,
        patch("curator.app.handler.count_uploads_in_batch") as mock_count_uploads,
    ):
        session = MockSession.return_value.__enter__.return_value

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

        mock_get_uploads.return_value = [upload]
        mock_count_uploads.return_value = 1

        await handler_instance.fetch_batch_uploads(FetchBatchUploadsData(batch_id=1))

        mock_sender.send_batch_uploads_list.assert_called_once()
        call_args = mock_sender.send_batch_uploads_list.call_args[0][0]
        # call_args is List[BatchUploadItem]
        assert len(call_args) == 1
        assert call_args[0].id == 1


@pytest.mark.asyncio
async def test_handle_fetch_images_api_error(handler_instance, mock_sender):
    with patch("curator.app.handler.MapillaryHandler") as MockHandler:
        handler = MockHandler.return_value

        # Create a mock response with a text property
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "500 error"

        # Raise HTTPStatusError
        error = httpx.HTTPStatusError(
            "Error message", request=MagicMock(), response=mock_response
        )
        handler.fetch_collection = AsyncMock(side_effect=error)

        await handler_instance.fetch_images("invalid_collection")

        # The handler should send the error message which includes response.text
        mock_sender.send_error.assert_called_once()
        args = mock_sender.send_error.call_args[0]
        assert "Mapillary API Error" in args[0]
        assert "500 error" in args[0]

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from curator.app.handler import Handler, WebSocketSender
from curator.app.messages import (
    UploadData,
    FetchBatchesPayload,
    FetchBatchUploadsPayload,
)
from curator.app.models import UploadItem


@pytest.fixture
def mock_sender():
    sender = MagicMock(spec=WebSocketSender)
    sender.send_json = AsyncMock()
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

        # Mock fetch_collection
        mock_image = MagicMock()
        mock_image.id = "img1"
        mock_image.creator.model_dump = MagicMock(return_value={"username": "creator1"})
        mock_image.model_dump = MagicMock(return_value={"id": "img1"})

        handler.fetch_collection.return_value = {"img1": mock_image}
        handler.fetch_existing_pages.return_value = {"img1": []}

        await handler_instance.fetch_images("some_input")

        assert mock_sender.send_json.call_count == 1
        call_args = mock_sender.send_json.call_args[0][0]
        assert call_args["type"] == "COLLECTION_IMAGES"
        assert "images" in call_args["data"]
        assert "creator" in call_args["data"]


@pytest.mark.asyncio
async def test_handle_fetch_images_not_found(handler_instance, mock_sender):
    with patch("curator.app.handler.MapillaryHandler") as MockHandler:
        handler = MockHandler.return_value
        handler.fetch_collection.return_value = {}

        await handler_instance.fetch_images("invalid")

        mock_sender.send_json.assert_called_once_with(
            {"type": "ERROR", "data": "Collection not found"}
        )


@pytest.mark.asyncio
async def test_handle_upload(handler_instance, mock_sender):
    with (
        patch("curator.app.handler.Session") as MockSession,
        patch("curator.app.handler.create_upload_request") as mock_create,
        patch("curator.app.handler.ingest_process_one") as mock_worker,
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

        mock_worker.delay.assert_called_once()
        mock_sender.send_json.assert_called_once()
        call_args = mock_sender.send_json.call_args[0][0]
        assert call_args["type"] == "UPLOAD_CREATED"
        assert call_args["data"][0]["id"] == 1


@pytest.mark.asyncio
async def test_handle_subscribe_batch(handler_instance, mock_sender):
    # Mock stream_uploads to return a coroutine
    mock_stream = AsyncMock()

    with patch.object(
        handler_instance, "stream_uploads", side_effect=mock_stream
    ) as mock_method:
        await handler_instance.subscribe_batch(123)

        mock_sender.send_json.assert_called_once_with(
            {"type": "SUBSCRIBED", "data": 123}
        )
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

        assert mock_sender.send_json.call_count == 2
        calls = mock_sender.send_json.call_args_list
        assert calls[0][0][0]["type"] == "UPLOADS_UPDATE"
        assert calls[1][0][0]["type"] == "UPLOADS_COMPLETE"


@pytest.mark.asyncio
async def test_handle_fetch_batches(handler_instance, mock_sender):
    with (
        patch("curator.app.handler.Session") as MockSession,
        patch("curator.app.handler.get_batches") as mock_get_batches,
        patch("curator.app.handler.count_batches") as mock_count_batches,
    ):
        session = MockSession.return_value.__enter__.return_value

        mock_batch = MagicMock()
        mock_batch.id = 1
        mock_batch.created_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_batch.user.username = "testuser"

        mock_upload = MagicMock()
        mock_upload.success = "success"
        mock_upload.error = None
        mock_upload.status = "completed"
        mock_batch.uploads = [mock_upload]
        mock_batch.userid = "user123"

        mock_get_batches.return_value = [mock_batch]
        mock_count_batches.return_value = 1

        await handler_instance.fetch_batches(FetchBatchesPayload(page=1, limit=10))

        mock_sender.send_json.assert_called_once()
        call_args = mock_sender.send_json.call_args[0][0]
        assert call_args["type"] == "BATCHES_LIST"
        assert len(call_args["data"]["items"]) == 1
        assert call_args["data"]["items"][0]["id"] == 1
        assert call_args["data"]["total"] == 1


@pytest.mark.asyncio
async def test_handle_fetch_batch_uploads(handler_instance, mock_sender):
    with (
        patch("curator.app.handler.Session") as MockSession,
        patch("curator.app.handler.get_upload_request") as mock_get_uploads,
        patch("curator.app.handler.count_uploads_in_batch") as mock_count_uploads,
    ):
        session = MockSession.return_value.__enter__.return_value

        mock_upload = MagicMock()
        mock_upload.key = "img1"
        mock_upload.model_dump.return_value = {"id": 1, "status": "completed"}

        mock_get_uploads.return_value = [mock_upload]
        mock_count_uploads.return_value = 1

        await handler_instance.fetch_batch_uploads(FetchBatchUploadsPayload(batch_id=1))

        mock_sender.send_json.assert_called_once()
        call_args = mock_sender.send_json.call_args[0][0]
        assert call_args["type"] == "BATCH_UPLOADS_LIST"
        assert len(call_args["data"]) == 1
        assert call_args["data"][0]["id"] == 1

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from curator.app.auth import check_login
from curator.asyncapi import Creator, Dates, GeoLocation, MediaImage
from curator.main import app
from curator.protocol import WS_CHANNEL_ADDRESS

client = TestClient(app)


# Override the login dependency
async def mock_check_login():
    return {
        "username": "testuser",
        "userid": "user123",
        "access_token": ("token", "secret"),
    }


app.dependency_overrides[check_login] = mock_check_login


@pytest.fixture
def mock_mapillary_handler():
    with patch("curator.app.handler.MapillaryHandler") as mock:
        yield mock


@pytest.fixture
def mock_dal():
    with (
        patch("curator.app.handler.create_upload_request") as mock_create,
        patch("curator.app.handler.get_upload_request") as mock_get,
        patch("curator.app.handler.count_uploads_in_batch") as mock_count,
    ):
        yield mock_create, mock_get, mock_count


@pytest.fixture
def mock_worker():
    with patch("curator.app.handler.process_upload") as mock_process_upload:
        yield mock_process_upload


@pytest.fixture
def mock_session():
    with patch("curator.app.handler.Session") as mock:
        session_instance = mock.return_value.__enter__.return_value
        yield session_instance


def test_ws_fetch_images(mock_mapillary_handler):
    mock_handler_instance = mock_mapillary_handler.return_value

    image = MediaImage(
        id="img1",
        title="Image 1",
        dates=Dates(taken="2023-01-01"),
        creator=Creator(id="c1", username="creator1", profile_url="http://profile"),
        url_original="http://original",
        thumbnail_url="http://thumb",
        preview_url="http://preview",
        url="http://url",
        width=100,
        height=100,
        description="desc",
        location=GeoLocation(latitude=10.0, longitude=10.0, compass_angle=0.0),
        camera_make="Canon",
        camera_model="EOS",
        is_pano=False,
        license="CC",
        tags=["tag1"],
        existing=[],
    )

    # Mock fetch_collection
    mock_handler_instance.fetch_collection = AsyncMock(return_value={"img1": image})

    # Mock fetch_existing_pages
    mock_handler_instance.fetch_existing_pages.return_value = {"img1": []}

    with client.websocket_connect(WS_CHANNEL_ADDRESS) as websocket:
        websocket.send_json({"type": "FETCH_IMAGES", "data": "some_input"})

        data = websocket.receive_json()
        assert data["type"] == "COLLECTION_IMAGES"
        assert "images" in data["data"]
        assert "creator" in data["data"]
        assert data["data"]["creator"] == {
            "id": "c1",
            "username": "creator1",
            "profile_url": "http://profile",
        }


def test_ws_fetch_images_not_found(mock_mapillary_handler):
    mock_handler_instance = mock_mapillary_handler.return_value
    # Return empty dict to trigger "Collection not found"
    mock_handler_instance.fetch_collection = AsyncMock(return_value={})

    with client.websocket_connect(WS_CHANNEL_ADDRESS) as websocket:
        websocket.send_json({"type": "FETCH_IMAGES", "data": "bad_input"})

        data = websocket.receive_json()
        assert data["type"] == "ERROR"
        assert data["data"] == "Collection not found"


def test_ws_upload(mocker, mock_dal, mock_worker, mock_session):
    mock_create, _, _ = mock_dal

    # Mock create_upload_request return value
    mock_req = mocker.MagicMock()
    mock_req.id = 1
    mock_req.status = "pending"
    mock_req.key = "img1"
    mock_req.batchid = 100

    mock_create.return_value = [mock_req]

    with (
        patch(
            "curator.app.handler.encrypt_access_token", return_value="encrypted_token"
        ),
        client.websocket_connect(WS_CHANNEL_ADDRESS) as websocket,
    ):
        websocket.send_json(
            {
                "type": "UPLOAD",
                "data": {
                    "items": [
                        {
                            "input": "test",
                            "id": "img1",
                            "title": "Test Title",
                            "wikitext": "Test Wikitext",
                        }
                    ],
                    "handler": "mapillary",
                },
            }
        )

        data = websocket.receive_json()
        assert data["type"] == "UPLOAD_CREATED"
        items = data["data"]
        assert len(items) == 1
        assert items[0]["id"] == 1
        assert items[0]["batchid"] == 100

        # Verify worker was called
        mock_worker.delay.assert_called_once_with(1)


def test_ws_invalid_message():
    with client.websocket_connect(WS_CHANNEL_ADDRESS) as websocket:
        websocket.send_json({"invalid": "json"})

        data = websocket.receive_json()
        assert data["type"] == "ERROR"
        assert data["data"] == "Invalid message format"


@pytest.mark.asyncio
async def test_stream_uploads_completion(mocker, mock_dal, mock_session):
    _, mock_get, mock_count = mock_dal

    # Setup mock data
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

    # Mock asyncio.sleep to avoid waiting
    with (
        patch("asyncio.sleep", new_callable=mocker.MagicMock) as mock_sleep,
        client.websocket_connect(WS_CHANNEL_ADDRESS) as websocket,
    ):
        mock_sleep.return_value = asyncio.Future()
        mock_sleep.return_value.set_result(None)

        # Send subscribe
        websocket.send_json({"type": "SUBSCRIBE_BATCH", "data": 123})

        # Expect SUBSCRIBED
        msg = websocket.receive_json()
        assert msg["type"] == "SUBSCRIBED"
        assert msg["data"] == 123

        # Expect UPLOADS_UPDATE
        msg = websocket.receive_json()
        assert msg["type"] == "UPLOADS_UPDATE"
        assert len(msg["data"]) == 1
        assert msg["data"][0]["status"] == "completed"

        # Expect UPLOADS_COMPLETE
        msg = websocket.receive_json()
        assert msg["type"] == "UPLOADS_COMPLETE"


def test_ws_subscribe_batches_list(mock_session):
    with (
        patch(
            "curator.app.handler_optimized.get_batches_optimized"
        ) as mock_get_batches,
        patch(
            "curator.app.handler_optimized.count_batches_optimized"
        ) as mock_count_batches,
        patch(
            "curator.app.handler_optimized.get_latest_update_time",
            return_value=datetime.now(),
        ),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        client.websocket_connect(WS_CHANNEL_ADDRESS) as websocket,
    ):
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        mock_get_batches.return_value = []
        mock_count_batches.return_value = 0

        websocket.send_json(
            {"type": "SUBSCRIBE_BATCHES_LIST", "data": {"userid": "u1", "filter": "f1"}}
        )

        # Should receive BATCHES_LIST
        data = websocket.receive_json()
        assert data["type"] == "BATCHES_LIST"
        assert data["data"]["items"] == []
        assert data["data"]["total"] == 0


def test_ws_fetch_batches_auto_subscribe(mock_session):
    with (
        patch(
            "curator.app.handler_optimized.get_batches_optimized"
        ) as mock_get_batches,
        patch(
            "curator.app.handler_optimized.count_batches_optimized"
        ) as mock_count_batches,
        patch(
            "curator.app.handler_optimized.get_latest_update_time",
            return_value=datetime.now(),
        ),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        client.websocket_connect(WS_CHANNEL_ADDRESS) as websocket,
    ):
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        mock_get_batches.return_value = []
        mock_count_batches.return_value = 0

        websocket.send_json(
            {
                "type": "FETCH_BATCHES",
                "data": {"page": 1, "limit": 10, "userid": "u1", "filter": "f1"},
            }
        )

        # Should receive BATCHES_LIST
        data = websocket.receive_json()
        assert data["type"] == "BATCHES_LIST"
        assert data["data"]["items"] == []
        assert data["data"]["total"] == 0

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import asyncio
from curator.main import app
from curator.app.auth import check_login

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
    with patch("curator.app.handler.ingest_process_one") as mock:
        yield mock


@pytest.fixture
def mock_session():
    with patch("curator.app.handler.Session") as mock:
        session_instance = mock.return_value.__enter__.return_value
        yield session_instance


def test_ws_fetch_images(mock_mapillary_handler):
    mock_handler_instance = mock_mapillary_handler.return_value

    # Mock fetch_collection
    mock_image = MagicMock()
    mock_image.id = "img1"
    mock_image.creator.model_dump = MagicMock(return_value={"username": "creator1"})
    # Also mock the model_dump of the image itself for to_jsonable
    mock_image.model_dump = MagicMock(return_value={"id": "img1", "lat": 10, "lon": 10})

    # Since we iterate over values, we need a dict
    mock_handler_instance.fetch_collection.return_value = {"img1": mock_image}

    # Mock fetch_existing_pages
    mock_handler_instance.fetch_existing_pages.return_value = {"img1": []}

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "FETCH_IMAGES", "data": "some_input"})

        data = websocket.receive_json()
        assert data["type"] == "COLLECTION_IMAGES"
        assert "images" in data["data"]
        assert "creator" in data["data"]
        assert data["data"]["creator"] == {"username": "creator1"}


def test_ws_fetch_images_not_found(mock_mapillary_handler):
    mock_handler_instance = mock_mapillary_handler.return_value
    mock_handler_instance.fetch_collection.return_value = {}

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "FETCH_IMAGES", "data": "invalid"})

        data = websocket.receive_json()
        assert data["type"] == "ERROR"
        assert data["data"] == "Collection not found"


def test_ws_upload(mock_dal, mock_worker, mock_session):
    mock_create, _, _ = mock_dal

    # Mock create_upload_request return value
    mock_req = MagicMock()
    mock_req.id = 1
    mock_req.status = "pending"
    mock_req.key = "img1"
    mock_req.batchid = 100

    mock_create.return_value = [mock_req]

    with patch(
        "curator.app.handler.encrypt_access_token", return_value="encrypted_token"
    ):
        with client.websocket_connect("/ws") as websocket:
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
            assert items[0]["batch_id"] == 100

        # Verify worker was called
        mock_worker.delay.assert_called_once_with(
            1, "test", "encrypted_token", "testuser"
        )


def test_ws_invalid_message():
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"invalid": "json"})

        data = websocket.receive_json()
        assert data["type"] == "ERROR"
        assert data["data"] == "Invalid message format"


@pytest.mark.asyncio
async def test_stream_uploads_completion(mock_dal, mock_session):
    _, mock_get, mock_count = mock_dal

    # Setup mock data
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

    # Mock asyncio.sleep to avoid waiting
    with patch("asyncio.sleep", new_callable=MagicMock) as mock_sleep:
        mock_sleep.return_value = asyncio.Future()
        mock_sleep.return_value.set_result(None)

        with client.websocket_connect("/ws") as websocket:
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
            assert msg["data"] == 123

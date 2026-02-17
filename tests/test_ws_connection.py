"""Tests for WebSocket connection handling."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from mwoauth import AccessToken

from curator.app.auth import check_login
from curator.main import app
from curator.protocol import WS_CHANNEL_ADDRESS

client = TestClient(app)


# Override the login dependency
async def mock_check_login():
    return {
        "username": "testuser",
        "userid": "user123",
        "access_token": AccessToken("token", "secret"),
    }


@pytest.fixture(autouse=True)
def setup_auth_override():
    # Set up dependency override before each test
    app.dependency_overrides[check_login] = mock_check_login
    yield
    # Clean up after test
    app.dependency_overrides.pop(check_login, None)


@pytest.fixture
def mock_dal():
    with (
        patch("curator.app.dal.create_upload_request") as mock_create,
        patch("curator.app.handler.get_upload_request") as mock_get,
        patch("curator.app.handler.count_uploads_in_batch") as mock_count,
    ):
        yield mock_create, mock_get, mock_count


@pytest.fixture
def mock_get_session_patch(patch_get_session):
    patch_get_session("curator.app.handler.get_session")
    patch_get_session("curator.app.handler_optimized.get_session")
    return True


@pytest.mark.asyncio
async def test_stream_uploads_completion(mocker, mock_dal, mock_get_session_patch):
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


def test_ws_subscribe_batches_list(mock_get_session_patch):
    """Test that SUBSCRIBE_BATCHES_LIST message starts streaming batches."""
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


def test_ws_fetch_batches_auto_subscribe(mock_get_session_patch):
    """Test that FETCH_BATCHES automatically subscribes to batch updates."""
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

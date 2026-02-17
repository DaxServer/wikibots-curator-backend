"""Tests for WebSocket message routing."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from mwoauth import AccessToken

from curator.app.auth import check_login
from curator.asyncapi import (
    CameraInfo,
    Creator,
    Dates,
    GeoLocation,
    ImageDimensions,
    ImageUrls,
    MediaImage,
)
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
def mock_mapillary_handler():
    with patch("curator.app.handler.MapillaryHandler") as mock:
        yield mock


def test_ws_fetch_images(mock_mapillary_handler):
    mock_handler_instance = mock_mapillary_handler.return_value

    image = MediaImage(
        id="img1",
        title="Image 1",
        dates=Dates(taken="2023-01-01"),
        creator=Creator(id="c1", username="creator1", profile_url="http://profile"),
        urls=ImageUrls(
            url="http://url",
            original="http://original",
            preview="http://preview",
            thumbnail="http://thumb",
        ),
        dimensions=ImageDimensions(width=100, height=100),
        camera=CameraInfo(make="Canon", model="EOS", is_pano=False),
        description="desc",
        location=GeoLocation(latitude=10.0, longitude=10.0),
        license="CC",
        tags=["tag1"],
        existing=[],
    )

    # Mock fetch_collection
    mock_handler_instance.fetch_collection = AsyncMock(return_value={"img1": image})

    # Mock fetch_existing_pages
    mock_handler_instance.fetch_existing_pages.return_value = {"img1": []}

    with client.websocket_connect(WS_CHANNEL_ADDRESS) as websocket:
        websocket.send_json(
            {"type": "FETCH_IMAGES", "data": "some_input", "handler": "mapillary"}
        )

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
    """Test that FETCH_IMAGES returns error for non-existent collection."""
    mock_handler_instance = mock_mapillary_handler.return_value
    # Return empty dict to trigger "Collection not found"
    mock_handler_instance.fetch_collection = AsyncMock(return_value={})

    with client.websocket_connect(WS_CHANNEL_ADDRESS) as websocket:
        websocket.send_json(
            {"type": "FETCH_IMAGES", "data": "bad_input", "handler": "mapillary"}
        )

        data = websocket.receive_json()
        assert data["type"] == "ERROR"
        assert data["data"] == "Collection not found"


def test_ws_invalid_message():
    """Test that invalid WebSocket message format returns error."""
    with client.websocket_connect(WS_CHANNEL_ADDRESS) as websocket:
        websocket.send_json({"invalid": "json"})

        data = websocket.receive_json()
        assert data["type"] == "ERROR"
        assert data["data"] == "Invalid message format"

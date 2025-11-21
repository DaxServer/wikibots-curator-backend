import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from curator.main import app
from curator.collections import ImagesRequest
from curator.app.image_models import Image, Creator, Dates, Location

client = TestClient(app)


@pytest.fixture
def mock_mapillary_handler():
    with patch("curator.collections.MapillaryHandler") as mock:
        yield mock


def test_post_collection_images_success(mock_mapillary_handler):
    mock_handler_instance = mock_mapillary_handler.return_value

    creator = Creator(id="user1", username="testuser", profile_url="http://profile")
    dates = Dates(taken=None)
    location = Location(latitude=0.0, longitude=0.0)
    image = Image(
        id="123",
        title="Test Image",
        dates=dates,
        creator=creator,
        location=location,
        url_original="http://original",
        thumbnail_url="http://thumb",
        preview_url="http://preview",
        url="http://url",
        width=100,
        height=100,
    )

    mock_handler_instance.fetch_collection.return_value = {"123": image}
    mock_handler_instance.fetch_existing_pages.return_value = {}

    payload = {"handler": "mapillary", "input": "valid_collection_id"}
    response = client.post("/api/collections/images", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "images" in data
    assert "creator" in data
    assert data["images"]["123"]["id"] == "123"


def test_post_collection_images_not_found(mock_mapillary_handler):
    mock_handler_instance = mock_mapillary_handler.return_value
    mock_handler_instance.fetch_collection.return_value = {}

    payload = {"handler": "mapillary", "input": "invalid_collection_id"}
    response = client.post("/api/collections/images", json=payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "Collection not found"

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from curator.collections import ImagesRequest, post_collection_images
from curator.app.image_models import Image, Creator, Dates, Location


@pytest.fixture
def mock_request():
    return MagicMock()


@pytest.fixture
def mock_mapillary_handler():
    with patch("curator.collections.MapillaryHandler") as mock:
        yield mock


@pytest.mark.asyncio
async def test_post_collection_images_success(mock_mapillary_handler, mock_request):
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

    payload = ImagesRequest(handler="mapillary", input="valid_collection_id")
    data = await post_collection_images(mock_request, payload)
    assert "images" in data
    assert "creator" in data
    assert data["images"]["123"].id == "123"


@pytest.mark.asyncio
async def test_post_collection_images_not_found(mock_mapillary_handler, mock_request):
    mock_handler_instance = mock_mapillary_handler.return_value
    mock_handler_instance.fetch_collection.return_value = {}

    payload = ImagesRequest(handler="mapillary", input="invalid_collection_id")
    with pytest.raises(HTTPException) as exc:
        await post_collection_images(mock_request, payload)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Collection not found"

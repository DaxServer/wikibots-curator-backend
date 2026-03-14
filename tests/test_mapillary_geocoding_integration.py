"""Tests for Mapillary handler geocoding integration."""

from unittest.mock import AsyncMock, patch

import pytest

from curator.asyncapi import (
    MediaImage,
)
from curator.handlers.mapillary_handler import MapillaryHandler


@pytest.fixture
def mock_sequence_data():
    """Mock Mapillary API sequence data response."""
    return {
        "img1": {
            "id": "img1",
            "geometry": {"coordinates": [-122.4194, 37.7749]},
            "creator": {"id": "u1", "username": "user1"},
            "captured_at": 1600000000000,
            "compass_angle": 180,
            "thumb_original_url": "http://original",
            "thumb_256_url": "http://thumb",
            "thumb_1024_url": "http://preview",
            "width": 100,
            "height": 100,
            "make": "Canon",
            "model": "EOS",
            "is_pano": False,
        },
        "img2": {
            "id": "img2",
            "geometry": {"coordinates": [-122.4294, 37.7849]},
            "creator": {"id": "u1", "username": "user1"},
            "captured_at": 1600000001000,
            "compass_angle": 90,
            "thumb_original_url": "http://original2",
            "thumb_256_url": "http://thumb2",
            "thumb_1024_url": "http://preview2",
            "width": 200,
            "height": 200,
            "make": "Nikon",
            "model": "D850",
            "is_pano": False,
        },
    }


@pytest.mark.asyncio
async def test_fetch_collection_calls_geocoding(mock_sequence_data):
    """Test that fetch_collection() calls reverse_geocode_batch()."""
    with (
        patch(
            "curator.handlers.mapillary_handler._fetch_sequence_data",
            new_callable=AsyncMock,
            return_value=mock_sequence_data,
        ),
        patch(
            "curator.handlers.mapillary_handler.reverse_geocode_batch",
            new_callable=AsyncMock,
        ) as mock_geocoding,
    ):
        handler = MapillaryHandler()
        result = await handler.fetch_collection("seq123")

        # Verify geocoding was called
        mock_geocoding.assert_called_once()

        # Get the images argument passed to reverse_geocode_batch
        call_args = mock_geocoding.call_args
        images = call_args[0][0]  # First positional argument

        # Verify it's a list of MediaImage objects
        assert isinstance(images, list)
        assert len(images) == 2
        assert all(isinstance(img, MediaImage) for img in images)

        # Verify the returned images
        assert isinstance(result, dict)
        assert len(result) == 2
        assert all(isinstance(img, MediaImage) for img in result.values())


@pytest.mark.asyncio
async def test_fetch_collection_enriches_geocoding_data(mock_sequence_data):
    """Test that fetch_collection() enriches images with geocoding data."""

    async def mock_geocode(images, http_client):
        """Mock geocoding that adds city and state to all images."""
        for image in images:
            if image.location:
                image.location.city = "San Francisco"
                image.location.state = "California"
                image.location.country = "United States"
                image.location.country_code = "us"
                image.location.county = "San Francisco County"
                image.location.postcode = "94102"

    with (
        patch(
            "curator.handlers.mapillary_handler._fetch_sequence_data",
            new_callable=AsyncMock,
            return_value=mock_sequence_data,
        ),
        patch(
            "curator.handlers.mapillary_handler.reverse_geocode_batch",
            new_callable=AsyncMock,
            side_effect=mock_geocode,
        ),
    ):
        handler = MapillaryHandler()
        result = await handler.fetch_collection("seq123")

        # Verify returned images have geocoding data
        assert result["img1"].location.city == "San Francisco"
        assert result["img1"].location.state == "California"
        assert result["img2"].location.city == "San Francisco"
        assert result["img2"].location.state == "California"


@pytest.mark.asyncio
async def test_fetch_collection_handles_geocoding_failure(mock_sequence_data):
    """Test that fetch_collection() returns images even when geocoding fails."""

    async def mock_geocode_fail(images, http_client):
        """Mock geocoding that fails for all images."""
        pass  # Don't add any geocoding data

    with (
        patch(
            "curator.handlers.mapillary_handler._fetch_sequence_data",
            new_callable=AsyncMock,
            return_value=mock_sequence_data,
        ),
        patch(
            "curator.handlers.mapillary_handler.reverse_geocode_batch",
            new_callable=AsyncMock,
            side_effect=mock_geocode_fail,
        ),
    ):
        handler = MapillaryHandler()
        result = await handler.fetch_collection("seq123")

        # Verify images are still returned with original location data
        assert len(result) == 2
        assert result["img1"].location.latitude == 37.7749
        assert result["img1"].location.longitude == -122.4194
        assert result["img1"].location.city is None  # No geocoding data

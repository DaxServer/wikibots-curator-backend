"""Tests for reverse geocoding functionality."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from curator.asyncapi import (
    CameraInfo,
    Creator,
    Dates,
    GeoLocation,
    ImageDimensions,
    ImageUrls,
    MediaImage,
)
from curator.core.geocoding import reverse_geocode, reverse_geocode_batch


@pytest.mark.asyncio
async def test_reverse_geocode_single_success():
    """Test that reverse_geocode() fetches and parses geocoding data correctly."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "address": {
            "city": "San Francisco",
            "county": "San Francisco County",
            "state": "California",
            "country": "United States",
            "country_code": "us",
            "postcode": "94102",
        }
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    semaphore = __import__("asyncio").Semaphore(5)

    result = await reverse_geocode(37.7749, -122.4194, mock_client, semaphore)

    assert result is not None
    assert result["city"] == "San Francisco"
    assert result["county"] == "San Francisco County"
    assert result["state"] == "California"
    assert result["country"] == "United States"
    assert result["country_code"] == "us"
    assert result["postcode"] == "94102"


@pytest.mark.asyncio
async def test_reverse_geocode_batch_concurrency():
    """Test that reverse_geocode_batch() processes multiple images correctly."""
    # Create 10 images with different coordinates
    images = []
    for i in range(10):
        images.append(
            MediaImage(
                id=f"img{i}",
                title=f"Image {i}",
                dates=Dates(taken="2023"),
                creator=Creator(id="user1", username="user1", profile_url="p"),
                location=GeoLocation(
                    latitude=37.7749 + i * 0.01, longitude=-122.4194 + i * 0.01
                ),
                urls=ImageUrls(url="u", original="o", preview="p", thumbnail="t"),
                camera=CameraInfo(is_pano=False),
                dimensions=ImageDimensions(width=100, height=100),
                existing=[],
            )
        )

    # Track number of API calls
    call_count = 0

    async def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1

        params = kwargs.get("params", {})
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "address": {
                "city": f"City {params.get('lat', 'unknown')}",
                "county": "County",
                "state": "State",
                "country": "Country",
                "country_code": "cc",
                "postcode": "12345",
            }
        }
        mock_response.raise_for_status = MagicMock()
        return mock_response

    mock_client = AsyncMock()
    mock_client.get = mock_get

    await reverse_geocode_batch(images, mock_client)

    # Verify all images were updated with geocoding data
    for i, image in enumerate(images):
        assert image.location.city is not None
        assert image.location.county == "County"
        assert image.location.state == "State"
        assert image.location.country == "Country"
        assert image.location.country_code == "cc"
        assert image.location.postcode == "12345"

    # Verify API was called for each image
    assert call_count == 10


@pytest.mark.asyncio
async def test_reverse_geocode_http_error():
    """Test that reverse_geocode() handles HTTP errors gracefully."""
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "Server error", request=MagicMock(), response=MagicMock(status_code=500)
    )

    semaphore = __import__("asyncio").Semaphore(5)

    result = await reverse_geocode(37.7749, -122.4194, mock_client, semaphore)

    assert result is None


@pytest.mark.asyncio
async def test_reverse_geocode_invalid_json():
    """Test that reverse_geocode() handles invalid JSON response gracefully."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("Invalid JSON")
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    semaphore = __import__("asyncio").Semaphore(5)

    result = await reverse_geocode(37.7749, -122.4194, mock_client, semaphore)

    assert result is None


@pytest.mark.asyncio
async def test_reverse_geocode_timeout():
    """Test that reverse_geocode() passes timeout parameter to HTTP client."""
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.TimeoutException("Request timeout")

    semaphore = __import__("asyncio").Semaphore(5)

    result = await reverse_geocode(37.7749, -122.4194, mock_client, semaphore)

    assert result is None
    # Verify timeout was passed to the HTTP client
    mock_client.get.assert_called_once()
    call_kwargs = mock_client.get.call_args.kwargs
    assert "timeout" in call_kwargs
    assert call_kwargs["timeout"] == 10.0


@pytest.mark.asyncio
async def test_reverse_geocode_batch_partial_failure():
    """Test that reverse_geocode_batch() continues even when some requests fail."""

    images = [
        MediaImage(
            id="img1",
            title="Image 1",
            dates=Dates(taken="2023"),
            creator=Creator(id="user1", username="user1", profile_url="p"),
            location=GeoLocation(latitude=37.7749, longitude=-122.4194),
            urls=ImageUrls(url="u", original="o", preview="p", thumbnail="t"),
            camera=CameraInfo(is_pano=False),
            dimensions=ImageDimensions(width=100, height=100),
            existing=[],
        ),
        MediaImage(
            id="img2",
            title="Image 2",
            dates=Dates(taken="2023"),
            creator=Creator(id="user1", username="user1", profile_url="p"),
            location=GeoLocation(latitude=37.7849, longitude=-122.4294),
            urls=ImageUrls(url="u", original="o", preview="p", thumbnail="t"),
            camera=CameraInfo(is_pano=False),
            dimensions=ImageDimensions(width=100, height=100),
            existing=[],
        ),
    ]

    call_count = 0

    async def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1

        # First request succeeds, second fails
        if call_count == 1:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "address": {
                    "city": "San Francisco",
                    "county": "San Francisco County",
                    "state": "California",
                    "country": "United States",
                    "country_code": "us",
                    "postcode": "94102",
                }
            }
            mock_response.raise_for_status = MagicMock()
            return mock_response
        else:
            raise httpx.TimeoutException("Request timeout")

    mock_client = AsyncMock()
    mock_client.get = mock_get

    await reverse_geocode_batch(images, mock_client)

    # First image should have geocoding data
    assert images[0].location.city == "San Francisco"
    assert images[0].location.state == "California"

    # Second image should have original location data (no geocoding)
    assert images[1].location.city is None
    assert images[1].location.state is None

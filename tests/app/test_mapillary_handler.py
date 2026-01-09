from unittest.mock import AsyncMock, patch

import pytest

from curator.app.handlers.mapillary_handler import MapillaryHandler
from curator.asyncapi import MediaImage


@pytest.fixture
def mock_fetch_sequence():
    with patch(
        "curator.app.handlers.mapillary_handler._fetch_sequence_data",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.fixture
def mock_cache():
    with patch("curator.app.handlers.mapillary_handler.cache") as mock:
        mock.set = AsyncMock()
        mock.set_many = AsyncMock()
        yield mock


@pytest.fixture
def mock_fetch_single():
    with patch(
        "curator.app.handlers.mapillary_handler._fetch_single_image",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


mock_image_data = {
    "id": "123",
    "geometry": {"coordinates": [10, 20]},
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
}


@pytest.mark.asyncio
async def test_fetch_image_metadata_sequence(mock_fetch_single, mock_cache):
    handler = MapillaryHandler()
    image_id = "123"
    sequence_id = "seq123"

    mock_fetch_single.return_value = mock_image_data

    result = await handler.fetch_image_metadata(image_id, sequence_id)

    assert isinstance(result, MediaImage)
    assert result.id == "123"
    # New design: it should just check individual cache
    mock_fetch_single.assert_called_once_with(image_id)


@pytest.mark.asyncio
async def test_fetch_image_metadata_single(mock_fetch_sequence, mock_fetch_single):
    handler = MapillaryHandler()
    image_id = "123"
    input_sequence = None

    mock_fetch_single.return_value = mock_image_data

    result = await handler.fetch_image_metadata(image_id, input_sequence)

    assert isinstance(result, MediaImage)
    assert result.id == "123"
    mock_fetch_single.assert_called_once_with(image_id)
    mock_fetch_sequence.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_collection_populates_caches(
    mock_fetch_sequence, mock_fetch_single, mock_cache
):
    handler = MapillaryHandler()
    sequence_id = "seq123"
    mock_fetch_sequence.return_value = {"123": mock_image_data}

    await handler.fetch_collection(sequence_id)

    # Verify sequence cache populated with IDs
    mock_cache.set.assert_called_once()
    args, kwargs = mock_cache.set.call_args
    assert args[0] == f"curator:mapillary:sequence:{sequence_id}"
    assert args[1] == ["123"]

    # Verify individual image cache populated
    mock_cache.set_many.assert_called_once()
    args, kwargs = mock_cache.set_many.call_args
    mapping = args[0]
    assert "curator:mapillary:image:123" in mapping
    assert mapping["curator:mapillary:image:123"] == mock_image_data


@pytest.mark.asyncio
async def test_fetch_images_batch_populates_caches(mock_cache):
    handler = MapillaryHandler()
    image_ids = ["123"]
    sequence_id = "seq1"

    with patch(
        "curator.app.handlers.mapillary_handler._fetch_images_by_ids_api",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = {"123": mock_image_data}

        await handler.fetch_images_batch(image_ids, sequence_id)

        # Verify individual image cache populated
        mock_cache.set_many.assert_called_once()
        args, kwargs = mock_cache.set_many.call_args
        mapping = args[0]
        assert "curator:mapillary:image:123" in mapping
        assert mapping["curator:mapillary:image:123"] == mock_image_data

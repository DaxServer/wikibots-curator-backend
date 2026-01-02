import hashlib
from unittest.mock import AsyncMock, patch

import pytest

from curator.app.handlers.mapillary_handler import (
    MapillaryHandler,
    _fetch_images_by_ids,
)
from curator.asyncapi import MediaImage


@pytest.fixture
def mock_fetch_sequence():
    with patch(
        "curator.app.handlers.mapillary_handler._fetch_sequence_data",
        new_callable=AsyncMock,
    ) as mock:
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
async def test_fetch_image_metadata_sequence(mock_fetch_sequence, mock_fetch_single):
    handler = MapillaryHandler()
    image_id = "123"
    sequence_id = "seq123"

    mock_fetch_sequence.return_value = {"123": mock_image_data}

    result = await handler.fetch_image_metadata(image_id, sequence_id)

    assert isinstance(result, MediaImage)
    assert result.id == "123"
    mock_fetch_sequence.assert_called_once_with(sequence_id)
    mock_fetch_single.assert_not_called()


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
async def test_fetch_image_metadata_fallback_not_implemented(
    mock_fetch_sequence, mock_fetch_single
):
    # This documents current behavior: if sequence provided but image not in it, it raises ValueError, NOT fallback.
    handler = MapillaryHandler()
    image_id = "123"
    sequence_id = "seq123"

    mock_fetch_sequence.return_value = {}  # Image not in sequence

    with pytest.raises(ValueError, match="Image data not found in sequence"):
        await handler.fetch_image_metadata(image_id, sequence_id)


@pytest.mark.asyncio
async def test_fetch_images_by_ids_hashing():
    image_ids = ["b", "a", "c"]
    sequence_id = "seq1"

    expected_sorted = ["a", "b", "c"]
    ids_str = ",".join(expected_sorted)
    expected_hash = hashlib.sha256(ids_str.encode()).hexdigest()

    with patch(
        "curator.app.handlers.mapillary_handler._fetch_images_internal",
        new_callable=AsyncMock,
    ) as mock_internal:
        mock_internal.return_value = {"a": {}, "b": {}, "c": {}}

        result = await _fetch_images_by_ids(image_ids, sequence_id)

        mock_internal.assert_called_once_with(
            expected_sorted, sequence_id, expected_hash
        )
        assert result == {"a": {}, "b": {}, "c": {}}


@pytest.mark.asyncio
async def test_fetch_images_by_ids_empty():
    result = await _fetch_images_by_ids([], "seq1")
    assert result == {}

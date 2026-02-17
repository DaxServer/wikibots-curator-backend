"""Tests for Mapillary image handler implementation."""

from unittest.mock import AsyncMock, patch

import pytest

from curator.asyncapi import MediaImage
from curator.handlers.mapillary_handler import (
    MapillaryHandler,
    from_mapillary,
)


@pytest.fixture
def mock_fetch_sequence():
    with patch(
        "curator.handlers.mapillary_handler._fetch_sequence_data",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.fixture
def mock_fetch_single():
    with patch(
        "curator.handlers.mapillary_handler._fetch_single_image",
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
async def test_fetch_image_metadata_sequence(mock_fetch_single):
    handler = MapillaryHandler()
    image_id = "123"
    sequence_id = "seq123"

    mock_fetch_single.return_value = mock_image_data

    result = await handler.fetch_image_metadata(image_id, sequence_id)

    assert isinstance(result, MediaImage)
    assert result.id == "123"


@pytest.mark.asyncio
async def test_fetch_image_metadata_single(mock_fetch_sequence, mock_fetch_single):
    handler = MapillaryHandler()
    image_id = "123"
    input_sequence = None

    mock_fetch_single.return_value = mock_image_data

    result = await handler.fetch_image_metadata(image_id, input_sequence)

    assert isinstance(result, MediaImage)
    assert result.id == "123"
    mock_fetch_sequence.assert_not_called()


@pytest.mark.parametrize(
    "make, model, expected_make, expected_model",
    [
        ("none", "EOS 5D", None, "EOS 5D"),
        ("Canon", "none", "Canon", None),
        ("none", "none", None, None),
    ],
)
def test_from_mapillary_converts_none_string(
    make, model, expected_make, expected_model
):
    data = mock_image_data.copy()
    data["make"] = make
    data["model"] = model

    result = from_mapillary(data)

    assert result.camera.make == expected_make
    assert result.camera.model == expected_model


@pytest.mark.parametrize(
    "compass_angle, expected_compass_angle",
    [
        (0, None),  # 0 should be omitted (not > 0)
        (360, None),  # 360 should be omitted (not < 360)
        (180, 180),  # 180 should be kept (0 < 180 < 360)
        (90, 90),  # 90 should be kept (0 < 90 < 360)
        (270, 270),  # 270 should be kept (0 < 270 < 360)
        (0.1, 0.1),  # 0.1 should be kept (0 < 0.1 < 360)
        (359.9, 359.9),  # 359.9 should be kept (0 < 359.9 < 360)
        (-90, None),  # negative should be omitted (not > 0)
        (450, None),  # > 360 should be omitted (not < 360)
        (-180, None),  # negative should be omitted (not > 0)
        (720, None),  # > 360 should be omitted (not < 360)
    ],
)
def test_from_mapillary_compass_angle_range(compass_angle, expected_compass_angle):
    """Test compass_angle is omitted when <= 0 or >= 360, kept otherwise"""
    data = mock_image_data.copy()
    data["compass_angle"] = compass_angle

    result = from_mapillary(data)

    assert result.location.compass_angle == expected_compass_angle

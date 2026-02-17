"""Tests for Flickr handler creation and configuration."""

import json
from pathlib import Path

import pytest

from curator.asyncapi import MediaImage
from curator.handlers.flickr_handler import from_flickr

# Load fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"
with open(FIXTURES_DIR / "flickr_api_response.json") as f:
    FLICKR_ALBUM_PAGE_RESPONSE = json.load(f)
FLICKR_PHOTO_WITHOUT_GEO = FLICKR_ALBUM_PAGE_RESPONSE["photoset"]["photo"][0]


@pytest.fixture
def mock_flickr_response():
    """Mock Flickr API response for album page"""
    return FLICKR_ALBUM_PAGE_RESPONSE


@pytest.fixture
def mock_flickr_photo_no_geo():
    """Mock Flickr photo without geo data"""
    return FLICKR_PHOTO_WITHOUT_GEO


class TestFromFlickr:
    """Test Flickr photo to MediaImage transformation"""

    def test_from_flickr_basic(self, mock_flickr_response):
        """Test basic photo transformation"""
        photo = mock_flickr_response["photoset"]["photo"][0]
        album_id = mock_flickr_response["photoset"]["id"]
        result = from_flickr(photo, album_id)

        assert isinstance(result, MediaImage)
        assert result.id == photo["id"]
        assert result.title.endswith(".jpg")
        assert result.dates.taken.startswith("2023-12-09")
        assert result.location.latitude == 0.0
        assert result.location.longitude == 0.0
        assert result.location.compass_angle is None
        assert result.urls.original == photo["url_o"]
        assert result.urls.preview == photo["url_l"]
        assert result.urls.thumbnail == photo["url_q"]
        assert result.dimensions.width == int(photo["width_o"])
        assert result.dimensions.height == int(photo["height_o"])

    def test_from_flickr_without_geo(self, mock_flickr_photo_no_geo):
        """Test photo without geo data uses defaults"""
        result = from_flickr(mock_flickr_photo_no_geo, "72177720313329606")

        assert result.location.latitude == 0.0
        assert result.location.longitude == 0.0
        assert result.location.compass_angle is None
        # When lat/lon are 0, accuracy is None (treated as no geo data)
        assert result.location.accuracy is None

    def test_from_flickr_with_geo(self, mock_flickr_response):
        """Test photo with actual geo data"""
        photoset = mock_flickr_response["photoset"]
        # Find the photo with actual geo coordinates (in nested geo object)
        photo = next(
            (
                p
                for p in photoset["photo"]
                if p.get("geo", {}).get("latitude") not in [0, None]
                and p.get("geo", {}).get("longitude") not in [0, None]
            ),
            None,
        )
        assert photo is not None, "No photo with geo data found in fixture"

        result = from_flickr(photo, photoset["id"])

        assert result.location.latitude == 37.7749
        assert result.location.longitude == -122.4194
        assert result.location.accuracy == 16

    def test_from_flickr_tags_parsing(self, mock_flickr_response):
        """Test tag extraction from space-separated string"""
        # Use the photo with tags from the fixture (the one we added)
        photoset = mock_flickr_response["photoset"]
        photo = next(
            (
                p
                for p in photoset["photo"]
                if p.get("tags") and "sports" in p.get("tags")
            )
        )
        result = from_flickr(photo, photoset["id"])

        assert result.tags == ["army", "navy", "football", "sports", "usaa"]

    def test_from_flickr_missing_id(self):
        """Test that missing id raises ValueError"""
        photo = {"title": "Test"}
        with pytest.raises(ValueError, match="missing 'id'"):
            from_flickr(photo, "album123")

    def test_from_flickr_missing_datetaken(self):
        """Test that missing datetaken raises ValueError"""
        photo = {"id": "123", "title": "Test"}
        with pytest.raises(ValueError, match="missing 'datetaken'"):
            from_flickr(photo, "album123")

    def test_from_flickr_missing_owner(self):
        """Test that missing owner raises ValueError"""
        photo = {"id": "123", "title": "Test", "datetaken": "2024-01-15 10:30:45"}
        with pytest.raises(ValueError, match="missing 'owner'"):
            from_flickr(photo, "album123")

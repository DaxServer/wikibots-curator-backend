import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from curator.asyncapi import MediaImage
from curator.handlers.flickr_handler import (
    FlickrHandler,
    fetch_photos_batch,
    from_flickr,
)

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


@pytest.fixture
def mock_fetch_details():
    """Mock _fetch_photo_details"""
    with patch(
        "curator.handlers.flickr_handler._fetch_photo_details",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


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
        assert result.location.compass_angle == 0.0
        assert result.url_original == photo["url_o"]
        assert result.preview_url == photo["url_l"]
        assert result.thumbnail_url == photo["url_q"]
        assert result.width == int(photo["width_o"])
        assert result.height == int(photo["height_o"])

    def test_from_flickr_without_geo(self, mock_flickr_photo_no_geo):
        """Test photo without geo data uses defaults"""
        result = from_flickr(mock_flickr_photo_no_geo, "72177720313329606")

        assert result.location.latitude == 0.0
        assert result.location.longitude == 0.0
        assert result.location.compass_angle == 0.0
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


class TestFetchPhotosBatch:
    """Test batch photo retrieval"""

    @pytest.mark.asyncio
    async def test_fetch_photos_batch_empty(self):
        """Test empty batch returns empty dict"""
        result = await fetch_photos_batch([], "album123", "user456")
        assert result == {}

    @pytest.mark.asyncio
    async def test_fetch_photos_batch(self):
        """Test batch photo retrieval"""
        image_ids = ["photo1", "photo2", "photo3"]
        album_id = "album123"
        user_id = "user456"

        mock_photos = {
            "photo1": {"id": "photo1", "title": "Photo 1"},
            "photo2": {"id": "photo2", "title": "Photo 2"},
            "photo3": {"id": "photo3", "title": "Photo 3"},
        }

        with patch(
            "curator.handlers.flickr_handler._fetch_photos_by_ids",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = mock_photos

            result = await fetch_photos_batch(image_ids, album_id, user_id)

            assert result == mock_photos
            mock_fetch.assert_called_once()


class TestFlickrHandler:
    """Test FlickrHandler class methods"""

    @pytest.mark.asyncio
    async def test_fetch_collection(self):
        """Test fetching all images from collection"""
        handler = FlickrHandler()
        url = "https://www.flickr.com/photos/25333247@N02/albums/72177720313329606"

        mock_ids = ["photo1", "photo2", "photo3"]

        mock_photos = {
            "photo1": {
                "id": "photo1",
                "title": "Photo 1",
                "datetaken": "2024-01-15 10:30:45",
                "owner": {
                    "nsid": "25333247@N02",
                    "username": "testuser",
                    "path_alias": "testuser",
                },
                "url_o": "http://o.jpg",
                "url_l": "http://l.jpg",
                "url_q": "http://q.jpg",
                "o_width": "1000",
                "o_height": "1000",
            },
            "photo2": {
                "id": "photo2",
                "title": "Photo 2",
                "datetaken": "2024-01-15 10:30:45",
                "owner": {
                    "nsid": "25333247@N02",
                    "username": "testuser",
                    "path_alias": "testuser",
                },
                "url_o": "http://o.jpg",
                "url_l": "http://l.jpg",
                "url_q": "http://q.jpg",
                "o_width": "1000",
                "o_height": "1000",
            },
            "photo3": {
                "id": "photo3",
                "title": "Photo 3",
                "datetaken": "2024-01-15 10:30:45",
                "owner": {
                    "nsid": "25333247@N02",
                    "username": "testuser",
                    "path_alias": "testuser",
                },
                "url_o": "http://o.jpg",
                "url_l": "http://l.jpg",
                "url_q": "http://q.jpg",
                "o_width": "1000",
                "o_height": "1000",
            },
        }

        with (
            patch(
                "curator.handlers.flickr_handler._fetch_album_ids",
                new_callable=AsyncMock,
            ) as mock_fetch_ids,
            patch(
                "curator.handlers.flickr_handler.fetch_photos_batch",
                new_callable=AsyncMock,
            ) as mock_fetch_batch,
        ):
            mock_fetch_ids.return_value = mock_ids

            mock_fetch_batch.return_value = mock_photos

            result = await handler.fetch_collection(url)

            assert isinstance(result, dict)
            assert len(result) == 3
            assert all(isinstance(v, MediaImage) for v in result.values())

    @pytest.mark.asyncio
    async def test_fetch_collection_ids(self):
        """Test fetching only IDs from collection"""
        handler = FlickrHandler()
        url = "https://www.flickr.com/photos/25333247@N02/albums/72177720313329606"

        mock_ids = ["photo1", "photo2", "photo3"]

        with patch(
            "curator.handlers.flickr_handler._fetch_album_ids",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = mock_ids

            result = await handler.fetch_collection_ids(url)

            assert result == mock_ids

    @pytest.mark.asyncio
    async def test_fetch_images_batch(self):
        """Test fetching images batch by IDs"""
        handler = FlickrHandler()
        collection = (
            "https://www.flickr.com/photos/25333247@N02/albums/72177720313329606"
        )
        image_ids = ["photo1", "photo2"]

        mock_photos = {
            "photo1": {
                "id": "photo1",
                "title": "Photo 1",
                "datetaken": "2024-01-15 10:30:45",
                "owner": {
                    "nsid": "25333247@N02",
                    "username": "testuser",
                    "path_alias": "testuser",
                },
                "url_o": "http://o.jpg",
                "url_l": "http://l.jpg",
                "url_q": "http://q.jpg",
                "o_width": "1000",
                "o_height": "1000",
            },
            "photo2": {
                "id": "photo2",
                "title": "Photo 2",
                "datetaken": "2024-01-15 10:30:45",
                "owner": {
                    "nsid": "25333247@N02",
                    "username": "testuser",
                    "path_alias": "testuser",
                },
                "url_o": "http://o.jpg",
                "url_l": "http://l.jpg",
                "url_q": "http://q.jpg",
                "o_width": "1000",
                "o_height": "1000",
            },
        }

        with patch(
            "curator.handlers.flickr_handler.fetch_photos_batch",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = mock_photos

            result = await handler.fetch_images_batch(image_ids, collection)

            assert isinstance(result, dict)
            assert len(result) == 2
            assert all(isinstance(v, MediaImage) for v in result.values())

    @pytest.mark.asyncio
    async def test_fetch_image_metadata_from_album(self, mock_fetch_details):
        """Test fetching image metadata from album"""
        handler = FlickrHandler()
        image_id = "photo1"
        url = "https://www.flickr.com/photos/25333247@N02/albums/72177720313329606"

        mock_ids = ["photo1", "photo2"]

        mock_photo = {
            "id": "photo1",
            "title": "Photo 1",
            "datetaken": "2024-01-15 10:30:45",
            "owner": {
                "nsid": "25333247@N02",
                "username": "testuser",
                "path_alias": "testuser",
            },
            "url_o": "http://o.jpg",
            "url_l": "http://l.jpg",
            "url_q": "http://q.jpg",
            "o_width": "1000",
            "o_height": "1000",
        }

        with (
            patch(
                "curator.handlers.flickr_handler._fetch_album_ids",
                new_callable=AsyncMock,
            ) as mock_fetch_ids,
        ):
            mock_fetch_ids.return_value = mock_ids
            mock_fetch_details.return_value = mock_photo

            result = await handler.fetch_image_metadata(image_id, url)

            assert isinstance(result, MediaImage)
            assert result.id == "photo1"

    @pytest.mark.asyncio
    async def test_fetch_image_metadata_fallback(self):
        """Test fetching individual photo metadata when not in album"""
        handler = FlickrHandler()
        image_id = "photo1"

        mock_photo = {
            "id": "photo1",
            "title": "Photo 1",
            "datetaken": "2024-01-15 10:30:45",
            "owner": {
                "nsid": "25333247@N02",
                "username": "testuser",
                "path_alias": "testuser",
            },
            "url_o": "http://o.jpg",
            "url_l": "http://l.jpg",
            "url_q": "http://q.jpg",
            "o_width": "1000",
            "o_height": "1000",
        }

        with patch(
            "curator.handlers.flickr_handler._fetch_photo_details",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = mock_photo

            result = await handler.fetch_image_metadata(image_id, None)

            assert isinstance(result, MediaImage)
            assert result.id == "photo1"
            mock_fetch.assert_called_once_with(image_id)

    @pytest.mark.asyncio
    async def test_fetch_existing_pages_empty(self):
        """Test that fetch_existing_pages returns empty dict"""
        handler = FlickrHandler()

        request = MagicMock()
        result = handler.fetch_existing_pages(["photo1", "photo2"], request)

        assert result == {}

"""Tests for Flickr metadata handling."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from curator.asyncapi import MediaImage
from curator.handlers.flickr_handler import FlickrHandler


@pytest.fixture
def mock_fetch_details():
    """Mock _fetch_photo_details"""
    with patch(
        "curator.handlers.flickr_handler._fetch_photo_details",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


class TestFlickrHandlerMetadata:
    """Test FlickrHandler metadata methods"""

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

    @pytest.mark.asyncio
    async def test_fetch_existing_pages_empty(self):
        """Test that fetch_existing_pages returns empty dict"""
        handler = FlickrHandler()

        request = MagicMock()
        result = handler.fetch_existing_pages(["photo1", "photo2"], request)

        assert result == {}

"""Tests for Flickr data fetching."""

from unittest.mock import AsyncMock, patch

import pytest

from curator.asyncapi import MediaImage
from curator.handlers.flickr_handler import FlickrHandler


class TestFlickrHandlerFetch:
    """Test FlickrHandler fetch methods"""

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

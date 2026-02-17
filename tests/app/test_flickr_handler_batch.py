"""Tests for Flickr handler batch operations."""

from unittest.mock import AsyncMock, patch

import pytest

from curator.handlers.flickr_handler import fetch_photos_batch


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

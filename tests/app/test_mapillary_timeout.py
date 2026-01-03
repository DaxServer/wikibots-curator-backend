from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from curator.app.config import cache
from curator.app.handlers.mapillary_handler import (
    _fetch_images_internal,
    _fetch_sequence_data,
    _fetch_sequence_ids,
    _fetch_single_image,
)


@pytest.fixture(autouse=True)
def disable_cache():
    cache.disable()
    yield
    cache.enable()


@pytest.mark.asyncio
async def test_fetch_sequence_data_timeout():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_client.get.return_value = mock_response

        await _fetch_sequence_data("seq123")

        mock_client.get.assert_called_once()
        args, kwargs = mock_client.get.call_args
        assert kwargs["timeout"] == 30


@pytest.mark.asyncio
async def test_fetch_sequence_ids_timeout():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_client.get.return_value = mock_response

        await _fetch_sequence_ids("seq123")

        mock_client.get.assert_called_once()
        args, kwargs = mock_client.get.call_args
        assert kwargs["timeout"] == 30


@pytest.mark.asyncio
async def test_fetch_images_internal_timeout():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_client.get.return_value = mock_response

        await _fetch_images_internal(["img1"], "seq123", "hash")

        mock_client.get.assert_called_once()
        args, kwargs = mock_client.get.call_args
        assert kwargs["timeout"] == 30


@pytest.mark.asyncio
async def test_fetch_single_image_timeout():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_client.get.return_value = mock_response

        await _fetch_single_image("img1")

        mock_client.get.assert_called_once()
        args, kwargs = mock_client.get.call_args
        assert kwargs["timeout"] == 30

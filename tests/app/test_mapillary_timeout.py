"""Tests for timeout handling in Mapillary requests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from curator.handlers.mapillary_handler import (
    _fetch_images_by_ids_api,
    _fetch_sequence_data,
    _fetch_single_image,
    _get_sequence_ids,
)


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


@pytest.mark.asyncio
async def test_get_sequence_ids_timeout():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_client.get.return_value = mock_response

        await _get_sequence_ids("seq123")

        mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_images_by_ids_api_timeout():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_client.get.return_value = mock_response

        await _fetch_images_by_ids_api(["img1"])

        mock_client.get.assert_called_once()


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

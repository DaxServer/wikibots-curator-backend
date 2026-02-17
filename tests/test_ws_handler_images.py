"""Tests for WebSocket handler image operations."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from curator.asyncapi import ImageHandler


@pytest.mark.asyncio
async def test_handle_fetch_images_success(handler_instance, mock_sender, mock_image):
    with patch("curator.app.handler.get_handler_for_handler_type") as mock_get_handler:
        mock_handler = MagicMock()
        mock_handler.fetch_collection = AsyncMock(return_value={"img1": mock_image})
        mock_handler.fetch_existing_pages.return_value = {"img1": []}
        mock_handler.name = "mapillary"
        mock_get_handler.return_value = mock_handler

        await handler_instance.fetch_images("some_input", ImageHandler.MAPILLARY)

        assert mock_sender.send_collection_images.call_count == 1
        call_args = mock_sender.send_collection_images.call_args[0][0]
        assert call_args.creator.username == mock_image.creator.username
        assert len(call_args.images) == 1


@pytest.mark.asyncio
async def test_handle_fetch_images_not_found(handler_instance, mock_sender):
    with patch("curator.app.handler.get_handler_for_handler_type") as mock_get_handler:
        mock_handler = MagicMock()
        mock_handler.fetch_collection = AsyncMock(return_value={})
        mock_handler.name = "mapillary"
        mock_get_handler.return_value = mock_handler

        await handler_instance.fetch_images("invalid", ImageHandler.MAPILLARY)

        mock_sender.send_error.assert_called_once_with("Collection not found")


@pytest.mark.asyncio
async def test_handle_fetch_images_api_error(mocker, handler_instance, mock_sender):
    with patch("curator.app.handler.get_handler_for_handler_type") as mock_get_handler:
        mock_handler = mocker.MagicMock()
        mock_handler.fetch_collection = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Error message",
                request=mocker.MagicMock(),
                response=mocker.MagicMock(status_code=502, text="502 error"),
            )
        )
        mock_handler.name = "mapillary"
        mock_get_handler.return_value = mock_handler

        await handler_instance.fetch_images(
            "invalid_collection", ImageHandler.MAPILLARY
        )

        mock_sender.send_error.assert_called_once()
        args = mock_sender.send_error.call_args[0]
        assert "Mapillary API Error" in args[0]
        assert "502 error" in args[0]

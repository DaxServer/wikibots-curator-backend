from unittest.mock import AsyncMock, patch

import httpx
import pytest

from curator.app.handler import Handler
from curator.asyncapi import (
    Creator,
    Dates,
    GeoLocation,
    MediaImage,
    PartialCollectionImagesData,
)


@pytest.fixture
def mock_sender(mocker):
    from curator.protocol import AsyncAPIWebSocket

    sender = mocker.MagicMock(spec=AsyncAPIWebSocket)
    sender.send_collection_images = AsyncMock()
    sender.send_error = AsyncMock()
    sender.send_try_batch_retrieval = AsyncMock()
    sender.send_collection_image_ids = AsyncMock()
    sender.send_partial_collection_images = AsyncMock()
    return sender


@pytest.fixture
def handler_instance(mocker, mock_user, mock_sender):
    return Handler(mock_user, mock_sender, mocker.MagicMock())


@pytest.mark.asyncio
async def test_fetch_images_batch_retrieval_on_500(
    handler_instance, mock_sender, mocker
):
    with patch("curator.app.handler.MapillaryHandler") as MockHandler:
        handler = MockHandler.return_value

        # 1. First call fails with 500
        mock_response = mocker.MagicMock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=mocker.MagicMock(),
            response=mock_response,
        )
        handler.fetch_collection.side_effect = error

        # 2. Subsequent calls for batch retrieval
        handler.fetch_collection_ids = AsyncMock(return_value=["id1", "id2"])

        image1 = MediaImage(
            id="id1",
            title="T1",
            url_original="u1",
            thumbnail_url="t1",
            preview_url="p1",
            url="l1",
            width=100,
            height=100,
            camera_make="M1",
            camera_model="MOD1",
            is_pano=False,
            location=GeoLocation(latitude=1, longitude=1, compass_angle=0),
            existing=[],
            creator=Creator(id="c1", username="u1", profile_url="p1"),
            dates=Dates(taken="2023-01-01"),
        )
        image2 = MediaImage(
            id="id2",
            title="T2",
            url_original="u2",
            thumbnail_url="t2",
            preview_url="p2",
            url="l2",
            width=100,
            height=100,
            camera_make="M2",
            camera_model="MOD2",
            is_pano=False,
            location=GeoLocation(latitude=2, longitude=2, compass_angle=0),
            existing=[],
            creator=Creator(id="c1", username="u1", profile_url="p1"),
            dates=Dates(taken="2023-01-01"),
        )

        handler.fetch_images_batch = AsyncMock(
            return_value={"id1": image1, "id2": image2}
        )

        handler.fetch_existing_pages.return_value = {"id1": [], "id2": []}

        await handler_instance.fetch_images("seq123")

        # Verify messages sent to frontend
        mock_sender.send_try_batch_retrieval.assert_called_once_with(
            "Large collection detected. Retrying in batches..."
        )
        mock_sender.send_collection_image_ids.assert_called_once_with(["id1", "id2"])

        # Verify partial images sent
        assert mock_sender.send_partial_collection_images.call_count == 1
        call_args = mock_sender.send_partial_collection_images.call_args[0][0]
        assert isinstance(call_args, PartialCollectionImagesData)
        assert call_args.collection == "seq123"
        assert len(call_args.images) == 2
        assert call_args.images[0].id == "id1"
        assert call_args.images[1].id == "id2"


@pytest.mark.asyncio
async def test_fetch_images_batch_retrieval_fail_after_ids(
    handler_instance, mock_sender, mocker
):
    with patch("curator.app.handler.MapillaryHandler") as MockHandler:
        handler = MockHandler.return_value

        # 1. First call fails with 500
        mock_response = mocker.MagicMock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=mocker.MagicMock(),
            response=mock_response,
        )
        handler.fetch_collection.side_effect = error

        # 2. fetch_collection_ids fails
        handler.fetch_collection_ids = AsyncMock(side_effect=Exception("API Down"))

        await handler_instance.fetch_images("seq123")

        mock_sender.send_try_batch_retrieval.assert_called_once()
        mock_sender.send_error.assert_called_once_with(
            "Batch retrieval failed: API Down"
        )


@pytest.mark.asyncio
async def test_fetch_images_batch_empty_collection(
    handler_instance, mock_sender, mocker
):
    with patch("curator.app.handler.MapillaryHandler") as MockHandler:
        handler = MockHandler.return_value

        # 1. First call fails with 500
        mock_response = mocker.MagicMock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=mocker.MagicMock(),
            response=mock_response,
        )
        handler.fetch_collection.side_effect = error

        # 2. fetch_collection_ids returns empty
        handler.fetch_collection_ids = AsyncMock(return_value=[])

        await handler_instance.fetch_images("seq123")

        mock_sender.send_try_batch_retrieval.assert_called_once()
        mock_sender.send_error.assert_called_with("Collection has no images")

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from curator.app.handler import Handler
from curator.asyncapi import (
    Creator,
    Dates,
    GeoLocation,
    ImageHandler,
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


def create_test_image(image_id: str) -> MediaImage:
    return MediaImage(
        id=image_id,
        title=f"T{image_id}",
        url_original=f"u{image_id}",
        thumbnail_url=f"t{image_id}",
        preview_url=f"p{image_id}",
        url=f"l{image_id}",
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


@pytest.mark.asyncio
async def test_fetch_images_batch_retrieval_on_500(
    handler_instance, mock_sender, mocker
):
    with patch("curator.app.handler.get_handler_for_handler_type") as mock_get_handler:
        handler = mock_get_handler.return_value

        mock_response = mocker.MagicMock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=mocker.MagicMock(),
            response=mock_response,
        )
        handler.fetch_collection.side_effect = error

        handler.fetch_collection_ids = AsyncMock(return_value=["id1", "id2"])

        image1 = create_test_image("id1")
        image2 = create_test_image("id2")

        handler.fetch_images_batch = AsyncMock(
            return_value={"id1": image1, "id2": image2}
        )

        handler.fetch_existing_pages.return_value = {"id1": [], "id2": []}

        await handler_instance.fetch_images("seq123", ImageHandler.MAPILLARY)

        mock_sender.send_try_batch_retrieval.assert_called_once_with(
            "Large collection detected. Loading in batches..."
        )
        mock_sender.send_collection_image_ids.assert_called_once_with(["id1", "id2"])

        assert mock_sender.send_partial_collection_images.call_count == 1
        call_args = mock_sender.send_partial_collection_images.call_args[0][0]
        assert isinstance(call_args, PartialCollectionImagesData)
        assert call_args.collection == "seq123"
        assert len(call_args.images) == 2
        assert call_args.images[0].id == "id1"
        assert call_args.images[1].id == "id2"


@pytest.mark.asyncio
async def test_fetch_images_batch_retrieval_on_timeout(
    handler_instance, mock_sender, mocker
):
    with patch("curator.app.handler.get_handler_for_handler_type") as mock_get_handler:
        handler = mock_get_handler.return_value

        handler.fetch_collection.side_effect = httpx.ReadTimeout(
            "Read timed out", request=mocker.MagicMock()
        )

        handler.fetch_collection_ids = AsyncMock(return_value=["id1", "id2"])

        image1 = create_test_image("id1")
        image2 = create_test_image("id2")

        handler.fetch_images_batch = AsyncMock(
            return_value={"id1": image1, "id2": image2}
        )

        handler.fetch_existing_pages.return_value = {"id1": [], "id2": []}

        await handler_instance.fetch_images("seq123", ImageHandler.MAPILLARY)

        mock_sender.send_try_batch_retrieval.assert_called_once_with(
            "Large collection detected. Loading in batches..."
        )
        mock_sender.send_collection_image_ids.assert_called_once_with(["id1", "id2"])

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
    with patch("curator.app.handler.get_handler_for_handler_type") as mock_get_handler:
        handler = mock_get_handler.return_value

        mock_response = mocker.MagicMock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=mocker.MagicMock(),
            response=mock_response,
        )
        handler.fetch_collection.side_effect = error

        handler.fetch_collection_ids = AsyncMock(side_effect=Exception("API Down"))

        await handler_instance.fetch_images("seq123", ImageHandler.MAPILLARY)

        mock_sender.send_try_batch_retrieval.assert_called_once()
        mock_sender.send_error.assert_called_once_with(
            "Batch retrieval failed: API Down"
        )


@pytest.mark.asyncio
async def test_fetch_images_batch_empty_collection(
    handler_instance, mock_sender, mocker
):
    with patch("curator.app.handler.get_handler_for_handler_type") as mock_get_handler:
        handler = mock_get_handler.return_value

        mock_response = mocker.MagicMock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=mocker.MagicMock(),
            response=mock_response,
        )
        handler.fetch_collection.side_effect = error

        handler.fetch_collection_ids = AsyncMock(return_value=[])

        await handler_instance.fetch_images("seq123", ImageHandler.MAPILLARY)

        mock_sender.send_try_batch_retrieval.assert_called_once()
        mock_sender.send_error.assert_called_with("Collection has no images")

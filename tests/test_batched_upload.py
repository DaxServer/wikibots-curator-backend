from unittest.mock import AsyncMock, patch

import pytest

from curator.app.handler import Handler
from curator.asyncapi import UploadItem, UploadSliceData


@pytest.fixture
def mock_sender(mocker):
    from curator.protocol import AsyncAPIWebSocket

    sender = mocker.MagicMock(spec=AsyncAPIWebSocket)
    sender.send_batch_created = AsyncMock()
    sender.send_upload_slice_ack = AsyncMock()
    sender.send_error = AsyncMock()
    return sender


@pytest.fixture
def handler_instance(mocker, mock_user, mock_sender, patch_get_session):
    patch_get_session("curator.app.handler.get_session")
    return Handler(mock_user, mock_sender, mocker.MagicMock())


@pytest.mark.asyncio
async def test_create_batch(mocker, handler_instance, mock_sender, mock_session):
    with (
        patch("curator.app.handler.ensure_user") as mock_ensure_user,
        patch("curator.app.handler.create_batch") as mock_create_batch,
    ):
        mock_batch = mocker.MagicMock()
        mock_batch.id = 123
        mock_create_batch.return_value = mock_batch

        await handler_instance.create_batch()

        mock_ensure_user.assert_called_once()
        mock_create_batch.assert_called_once()
        mock_sender.send_batch_created.assert_called_once_with(123)


@pytest.mark.asyncio
async def test_upload_slice(mocker, handler_instance, mock_sender, mock_session):
    with (
        patch(
            "curator.app.handler.create_upload_requests_for_batch"
        ) as mock_create_reqs,
        patch("curator.app.handler.process_upload") as mock_process_upload,
        patch("curator.app.handler.encrypt_access_token", return_value="encrypted"),
    ):
        mock_req = mocker.MagicMock()
        mock_req.id = 1
        mock_create_reqs.return_value = [mock_req]

        data = UploadSliceData(
            batchid=123,
            sliceid=0,
            handler="mapillary",
            items=[UploadItem(id="img1", input="test", title="T", wikitext="W")],
        )

        await handler_instance.upload_slice(data)

        mock_create_reqs.assert_called_once()
        mock_process_upload.delay.assert_called_once_with(1)
        mock_sender.send_upload_slice_ack.assert_called_once_with(0)


@pytest.mark.asyncio
async def test_upload_slice_multiple_items(
    mocker, handler_instance, mock_sender, mock_session
):
    with (
        patch(
            "curator.app.handler.create_upload_requests_for_batch"
        ) as mock_create_reqs,
        patch("curator.app.handler.process_upload") as mock_process_upload,
        patch("curator.app.handler.encrypt_access_token", return_value="encrypted"),
    ):
        mock_req1 = mocker.MagicMock()
        mock_req1.id = 1
        mock_req2 = mocker.MagicMock()
        mock_req2.id = 2
        mock_create_reqs.return_value = [mock_req1, mock_req2]

        data = UploadSliceData(
            batchid=123,
            sliceid=1,
            handler="mapillary",
            items=[
                UploadItem(id="img1", input="test", title="T1", wikitext="W1"),
                UploadItem(id="img2", input="test", title="T2", wikitext="W2"),
            ],
        )

        await handler_instance.upload_slice(data)

        mock_create_reqs.assert_called_once()
        # Verify process_upload.delay was called twice with the correct IDs
        assert mock_process_upload.delay.call_count == 2
        calls = mock_process_upload.delay.call_args_list
        assert calls[0][0][0] == 1
        assert calls[1][0][0] == 2
        mock_sender.send_upload_slice_ack.assert_called_once_with(1)

from unittest.mock import AsyncMock, patch

import pytest

from curator.app.handler import Handler
from curator.asyncapi import UploadItem, UploadSliceData
from curator.workers.rq import QueuePriority


@pytest.fixture
def mock_sender(mocker):
    from curator.protocol import AsyncAPIWebSocket

    sender = mocker.MagicMock(spec=AsyncAPIWebSocket)
    sender.send_batch_created = AsyncMock()
    sender.send_upload_slice_ack = AsyncMock()
    sender.send_error = AsyncMock()
    return sender


@pytest.fixture
def handler_instance(mocker, mock_user, mock_sender):
    return Handler(mock_user, mock_sender, mocker.MagicMock())


@pytest.mark.asyncio
async def test_create_batch(mocker, handler_instance, mock_sender, mock_session):
    with (
        patch("curator.app.handler.get_session", return_value=iter([mock_session])),
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
        patch("curator.app.handler.get_session", return_value=iter([mock_session])),
        patch(
            "curator.app.handler.create_upload_requests_for_batch"
        ) as mock_create_reqs,
        patch("curator.app.handler.get_queue") as mock_get_queue,
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
        mock_get_queue.assert_called_once_with(QueuePriority.NORMAL)
        mock_queue = mock_get_queue.return_value
        mock_queue.enqueue_many.assert_called_once()
        mock_sender.send_upload_slice_ack.assert_called_once_with(0)


@pytest.mark.asyncio
async def test_upload_slice_multiple_items(
    mocker, handler_instance, mock_sender, mock_session
):
    with (
        patch("curator.app.handler.get_session", return_value=iter([mock_session])),
        patch(
            "curator.app.handler.create_upload_requests_for_batch"
        ) as mock_create_reqs,
        patch("curator.app.handler.get_queue") as mock_get_queue,
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
        mock_get_queue.assert_called_once_with(QueuePriority.NORMAL)
        mock_queue = mock_get_queue.return_value
        mock_queue.enqueue_many.assert_called_once()
        # Verify enqueue_many was called with 2 items
        enqueued_args = mock_queue.enqueue_many.call_args[0][0]
        assert len(enqueued_args) == 2
        mock_sender.send_upload_slice_ack.assert_called_once_with(1)

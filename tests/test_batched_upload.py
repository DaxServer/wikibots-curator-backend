from unittest.mock import patch

import pytest

from curator.asyncapi import UploadItem, UploadSliceAckItem, UploadSliceData


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
        # Mock both delay and apply_async
        mock_process_upload.delay = mocker.MagicMock()
        mock_process_upload.apply_async = mocker.MagicMock()

        mock_req = mocker.MagicMock()
        mock_req.id = 1
        mock_req.key = "img1"
        mock_req.status = "queued"
        mock_create_reqs.return_value = [mock_req]

        data = UploadSliceData(
            batchid=123,
            sliceid=0,
            handler="mapillary",
            items=[UploadItem(id="img1", input="test", title="T", wikitext="W")],
        )

        await handler_instance.upload_slice(data)

        mock_create_reqs.assert_called_once()
        # Check that process_upload methods were called once (delay or apply_async)
        total_calls = (
            mock_process_upload.delay.call_count
            + mock_process_upload.apply_async.call_count
        )
        assert total_calls == 1

        # Check the call arguments (works for both delay and apply_async)
        if mock_process_upload.delay.call_count > 0:
            call_args = mock_process_upload.delay.call_args[0]
            assert call_args[0] == 1  # First arg is upload_id
            assert len(call_args) == 2  # Called with 2 args (upload_id, edit_group_id)
            assert isinstance(call_args[1], str)  # Second arg is edit_group_id string
            assert len(call_args[1]) == 12  # edit_group_id is 12 characters
        else:
            # apply_async uses args as keyword argument
            call_args = mock_process_upload.apply_async.call_args
            assert call_args[1]["args"][0] == 1  # First arg is upload_id
            assert len(call_args[1]["args"]) == 2  # Called with 2 args
            assert isinstance(
                call_args[1]["args"][1], str
            )  # Second arg is edit_group_id string
            assert len(call_args[1]["args"][1]) == 12  # edit_group_id is 12 characters

        mock_sender.send_upload_slice_ack.assert_called_once_with(
            data=[UploadSliceAckItem(id="img1", status="queued")], sliceid=0
        )


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
        # Mock both delay and apply_async
        mock_process_upload.delay = mocker.MagicMock()
        mock_process_upload.apply_async = mocker.MagicMock()

        mock_req1 = mocker.MagicMock()
        mock_req1.id = 1
        mock_req1.key = "img1"
        mock_req1.status = "queued"
        mock_req2 = mocker.MagicMock()
        mock_req2.id = 2
        mock_req2.key = "img2"
        mock_req2.status = "queued"
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
        # Verify process_upload methods were called twice total (delay or apply_async)
        total_calls = (
            mock_process_upload.delay.call_count
            + mock_process_upload.apply_async.call_count
        )
        assert total_calls == 2

        # Verify send_upload_slice_ack was called with data and sliceid
        mock_sender.send_upload_slice_ack.assert_called_once()
        call_args = mock_sender.send_upload_slice_ack.call_args
        # Check both positional and keyword arguments
        if len(call_args[0]) > 0:
            data_arg = call_args[0][0]
        else:
            data_arg = call_args[1].get("data")
        if len(call_args[0]) > 1:
            sliceid_arg = call_args[0][1]
        else:
            sliceid_arg = call_args[1].get("sliceid")
        assert data_arg == [
            UploadSliceAckItem(id="img1", status="queued"),
            UploadSliceAckItem(id="img2", status="queued"),
        ]
        assert sliceid_arg == 1

"""Tests for batch upload operations."""

from unittest.mock import MagicMock, patch

import pytest

from curator.asyncapi import UploadItem, UploadSliceAckItem, UploadSliceData
from curator.core.rate_limiter import RateLimitInfo


@pytest.mark.asyncio
async def test_create_batch(mocker, handler_instance, mock_sender, mock_session):
    with (
        patch("curator.core.handler.ensure_user") as mock_ensure_user,
        patch("curator.core.handler.create_batch") as mock_create_batch,
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
    mock_batch = mocker.MagicMock()
    mock_batch.id = 123
    mock_batch.edit_group_id = "abc123def456"
    mock_session.get.return_value = mock_batch

    with (
        patch(
            "curator.core.handler.create_upload_requests_for_batch"
        ) as mock_create_reqs,
        patch("curator.core.task_enqueuer.process_upload") as mock_process_upload,
        patch("curator.core.handler.encrypt_access_token", return_value="encrypted"),
        patch(
            "curator.core.task_enqueuer.get_rate_limit_for_batch"
        ) as mock_get_rate_limit,
        patch("curator.core.task_enqueuer.get_next_upload_delay") as mock_get_delay,
        patch("curator.core.task_enqueuer.register_user_queue"),
    ):
        mock_process_upload.apply_async = mocker.MagicMock(
            return_value=MagicMock(id="task-1")
        )

        mock_get_rate_limit.return_value = RateLimitInfo(
            uploads_per_period=999, period_seconds=1
        )
        mock_get_delay.return_value = 0.0

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
        assert mock_process_upload.apply_async.call_count == 1

        call_kwargs = mock_process_upload.apply_async.call_args[1]
        assert call_kwargs["args"][0] == 1
        assert len(call_kwargs["args"]) == 3
        assert call_kwargs["args"][1] == "abc123def456"
        assert call_kwargs["args"][2] == "user123"
        assert call_kwargs["queue"] == "uploads-user123"

        mock_sender.send_upload_slice_ack.assert_called_once_with(
            data=[UploadSliceAckItem(id="img1", status="queued")], sliceid=0
        )


@pytest.mark.asyncio
async def test_upload_slice_multiple_items(
    mocker, handler_instance, mock_sender, mock_session
):
    mock_batch = mocker.MagicMock()
    mock_batch.id = 123
    mock_batch.edit_group_id = "xyz789uvw012"
    mock_session.get.return_value = mock_batch

    with (
        patch(
            "curator.core.handler.create_upload_requests_for_batch"
        ) as mock_create_reqs,
        patch("curator.core.task_enqueuer.process_upload") as mock_process_upload,
        patch("curator.core.handler.encrypt_access_token", return_value="encrypted"),
        patch(
            "curator.core.task_enqueuer.get_rate_limit_for_batch"
        ) as mock_get_rate_limit,
        patch("curator.core.task_enqueuer.get_next_upload_delay") as mock_get_delay,
        patch("curator.core.task_enqueuer.register_user_queue"),
    ):
        mock_process_upload.apply_async = mocker.MagicMock(
            return_value=MagicMock(id="task-1")
        )

        mock_get_rate_limit.return_value = RateLimitInfo(
            uploads_per_period=999, period_seconds=1
        )
        mock_get_delay.return_value = 0.0

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
        assert mock_process_upload.apply_async.call_count == 2
        for call in mock_process_upload.apply_async.call_args_list:
            assert call[1]["queue"] == "uploads-user123"
            assert call[1]["args"][1] == "xyz789uvw012"
            assert call[1]["args"][2] == "user123"

        mock_sender.send_upload_slice_ack.assert_called_once()
        call_args = mock_sender.send_upload_slice_ack.call_args
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

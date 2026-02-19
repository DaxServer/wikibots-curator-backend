"""Tests for batch upload operations."""

from unittest.mock import patch

import pytest

from curator.app.rate_limiter import RateLimitInfo
from curator.asyncapi import UploadItem, UploadSliceAckItem, UploadSliceData
from curator.workers.celery import QUEUE_NORMAL, QUEUE_PRIVILEGED


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
    # Mock batch with edit_group_id
    mock_batch = mocker.MagicMock()
    mock_batch.id = 123
    mock_batch.edit_group_id = "abc123def456"
    mock_session.get.return_value = mock_batch

    with (
        patch(
            "curator.app.handler.create_upload_requests_for_batch"
        ) as mock_create_reqs,
        patch("curator.app.task_enqueuer.process_upload") as mock_process_upload,
        patch("curator.app.handler.encrypt_access_token", return_value="encrypted"),
        patch(
            "curator.app.task_enqueuer.get_rate_limit_for_batch"
        ) as mock_get_rate_limit,
        patch("curator.app.task_enqueuer.get_next_upload_delay") as mock_get_delay,
    ):
        # Mock both delay and apply_async
        mock_process_upload.delay = mocker.MagicMock()
        mock_process_upload.apply_async = mocker.MagicMock()

        # Mock rate limiter to return privileged user (no delay)
        mock_get_rate_limit.return_value = RateLimitInfo(
            uploads_per_period=999, period_seconds=1, is_privileged=True
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
        # Check that process_upload.apply_async was called once
        assert mock_process_upload.apply_async.call_count == 1

        # Check the call arguments (apply_async uses kwargs)
        call_kwargs = mock_process_upload.apply_async.call_args[1]
        assert call_kwargs["args"][0] == 1  # First arg is upload_id
        assert len(call_kwargs["args"]) == 2  # Called with 2 args
        assert isinstance(
            call_kwargs["args"][1], str
        )  # Second arg is edit_group_id string
        assert len(call_kwargs["args"][1]) == 12  # edit_group_id is 12 characters
        assert call_kwargs["args"][1] == "abc123def456"  # Uses batch's edit_group_id
        assert call_kwargs["queue"] in [
            QUEUE_PRIVILEGED,
            QUEUE_NORMAL,
        ]  # Check queue parameter

        mock_sender.send_upload_slice_ack.assert_called_once_with(
            data=[UploadSliceAckItem(id="img1", status="queued")], sliceid=0
        )


@pytest.mark.asyncio
async def test_upload_slice_multiple_items(
    mocker, handler_instance, mock_sender, mock_session
):
    # Mock batch with edit_group_id
    mock_batch = mocker.MagicMock()
    mock_batch.id = 123
    mock_batch.edit_group_id = "xyz789uvw012"
    mock_session.get.return_value = mock_batch

    with (
        patch(
            "curator.app.handler.create_upload_requests_for_batch"
        ) as mock_create_reqs,
        patch("curator.app.task_enqueuer.process_upload") as mock_process_upload,
        patch("curator.app.handler.encrypt_access_token", return_value="encrypted"),
        patch(
            "curator.app.task_enqueuer.get_rate_limit_for_batch"
        ) as mock_get_rate_limit,
        patch("curator.app.task_enqueuer.get_next_upload_delay") as mock_get_delay,
    ):
        # Mock both delay and apply_async
        mock_process_upload.delay = mocker.MagicMock()
        mock_process_upload.apply_async = mocker.MagicMock()

        # Mock rate limiter to return privileged user (no delay)
        mock_get_rate_limit.return_value = RateLimitInfo(
            uploads_per_period=999, period_seconds=1, is_privileged=True
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
        # Verify process_upload.apply_async was called twice
        assert mock_process_upload.apply_async.call_count == 2
        # Verify both calls have queue parameter and use batch's edit_group_id
        for call in mock_process_upload.apply_async.call_args_list:
            assert call[1]["queue"] in [QUEUE_PRIVILEGED, QUEUE_NORMAL]
            assert call[1]["args"][1] == "xyz789uvw012"  # Uses batch's edit_group_id

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

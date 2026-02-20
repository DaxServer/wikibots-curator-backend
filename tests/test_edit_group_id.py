"""Tests for edit_group_id functionality on batches."""

from unittest.mock import MagicMock, patch

import pytest
from mwoauth.tokens import AccessToken

from curator.admin import admin_retry_uploads
from curator.app.crypto import generate_edit_group_id
from curator.app.dal import create_batch
from curator.app.models import Batch, RetrySelectedUploadsRequest
from curator.app.rate_limiter import RateLimitInfo
from curator.asyncapi import UploadItem, UploadSliceData
from curator.workers.celery import QUEUE_PRIVILEGED


class TestBatchModelEditGroupId:
    """Test Batch model has edit_group_id field"""

    def test_batch_model_has_edit_group_id_field(self):
        """Verify Batch model includes edit_group_id field"""
        assert "edit_group_id" in Batch.model_fields

    def test_edit_group_id_is_optional(self):
        """Verify edit_group_id is optional (can be None)"""
        batch = Batch(userid="user123")
        assert batch.edit_group_id is None

    def test_edit_group_id_can_be_set(self):
        """Verify edit_group_id can be set on a batch"""
        test_id = "abc123def456"
        batch = Batch(userid="user123", edit_group_id=test_id)
        assert batch.edit_group_id == test_id


class TestEditGroupIdGeneration:
    """Test edit_group_id generation function"""

    def test_generate_edit_group_id_returns_12_chars(self):
        """Verify generated edit_group_id is 12 characters"""
        edit_id = generate_edit_group_id()
        assert len(edit_id) == 12

    def test_generate_edit_group_id_is_alphanumeric(self):
        """Verify generated edit_group_id is alphanumeric (hexdigits)"""
        edit_id = generate_edit_group_id()
        assert edit_id.isalnum()

    def test_generate_edit_group_id_is_hex(self):
        """Verify generated edit_group_id uses hex characters (0-9, a-f)"""
        edit_id = generate_edit_group_id()
        assert all(c.lower() in "0123456789abcdef" for c in edit_id)

    def test_generate_edit_group_id_is_unique(self):
        """Verify generate_edit_group_id produces unique values"""
        ids = {generate_edit_group_id() for _ in range(100)}
        assert len(ids) == 100


class TestBatchCreationEditGroupId:
    """Test batch creation generates edit_group_id"""

    @patch("curator.app.dal.generate_edit_group_id")
    def test_create_batch_generates_edit_group_id(self, mock_gen_id, mock_session):
        """Verify creating a batch generates a unique edit_group_id"""
        mock_gen_id.return_value = "abc123def456"

        batch = create_batch(
            session=mock_session,
            userid="user123",
            username="testuser",
        )

        mock_gen_id.assert_called_once()
        assert batch.edit_group_id == "abc123def456"

    @patch("curator.app.dal.generate_edit_group_id")
    def test_different_batches_have_different_edit_group_ids(
        self, mock_gen_id, mock_session
    ):
        """Verify creating multiple batches results in different edit_group_ids"""
        mock_gen_id.side_effect = ["abc123def456", "xyz789uvw012"]

        batch1 = create_batch(
            session=mock_session,
            userid="user123",
            username="testuser",
        )
        batch2 = create_batch(
            session=mock_session,
            userid="user123",
            username="testuser",
        )

        assert batch1.edit_group_id == "abc123def456"
        assert batch2.edit_group_id == "xyz789uvw012"
        assert batch1.edit_group_id != batch2.edit_group_id


class TestUploadSliceUsesBatchEditGroupId:
    """Test upload_slice uses batch's edit_group_id"""

    @pytest.mark.asyncio
    async def test_upload_slice_uses_batch_edit_group_id(
        self, mocker, handler_instance, mock_session
    ):
        """Verify uploads in same batch share the batch's edit_group_id"""
        mock_batch = MagicMock()
        mock_batch.id = 123
        mock_batch.edit_group_id = "abc123def456"
        mock_session.get.return_value = mock_batch

        mock_req = mocker.MagicMock()
        mock_req.id = 1
        mock_req.key = "img1"
        mock_req.status = "queued"

        with (
            patch(
                "curator.app.handler.create_upload_requests_for_batch"
            ) as mock_create,
            patch("curator.app.handler.encrypt_access_token", return_value="encrypted"),
            patch(
                "curator.app.task_enqueuer.get_rate_limit_for_batch"
            ) as mock_get_rate,
            patch("curator.app.task_enqueuer.get_next_upload_delay", return_value=0.0),
            patch("curator.app.task_enqueuer.process_upload") as mock_process,
        ):
            mock_create.return_value = [mock_req]
            mock_get_rate.return_value = RateLimitInfo(
                uploads_per_period=999, period_seconds=1, is_privileged=True
            )
            mock_process.apply_async = mocker.MagicMock()

            data = UploadSliceData(
                batchid=123,
                sliceid=0,
                handler="mapillary",
                items=[UploadItem(id="img1", input="test", title="T", wikitext="W")],
            )

            await handler_instance.upload_slice(data)

            mock_process.apply_async.assert_called_once()
            call_kwargs = mock_process.apply_async.call_args[1]
            assert call_kwargs["args"][1] == "abc123def456"


class TestRetryCreatesNewBatch:
    """Test retries create new batches with their own edit_group_id"""

    @pytest.mark.asyncio
    async def test_user_retry_creates_new_batch_with_edit_group_id(
        self, mocker, handler_instance
    ):
        """Verify user retry creates a new batch with its own edit_group_id"""
        with (
            patch(
                "curator.app.handler.reset_failed_uploads_to_new_batch"
            ) as mock_reset,
            patch("curator.app.task_enqueuer.process_upload") as mock_process,
            patch(
                "curator.app.task_enqueuer.get_rate_limit_for_batch"
            ) as mock_get_rate,
            patch("curator.app.task_enqueuer.get_next_upload_delay") as mock_get_delay,
        ):
            mock_reset.return_value = ([1, 2], "newbatch123456")
            mock_get_rate.return_value = RateLimitInfo(
                uploads_per_period=999, period_seconds=1, is_privileged=False
            )
            mock_get_delay.return_value = 0.0
            mock_process.apply_async = mocker.MagicMock()

            await handler_instance.retry_uploads(123)

            mock_reset.assert_called_once()
            assert mock_process.apply_async.call_count == 2
            for call in mock_process.apply_async.call_args_list:
                call_kwargs = call[1]
                assert call_kwargs["args"][1] == "newbatch123456"

    @pytest.mark.asyncio
    async def test_admin_retry_creates_new_batches_with_edit_group_id(
        self, mocker, mock_session
    ):
        """Verify admin retry creates new batches for uploads with their own edit_group_id"""
        user = {
            "username": "DaxServer",
            "userid": "admin1",
            "access_token": AccessToken("token", "secret"),
        }
        request = RetrySelectedUploadsRequest(upload_ids=[1, 2, 3])

        with (
            patch("curator.admin.retry_selected_uploads_to_new_batch") as mock_retry,
            patch("curator.workers.tasks.process_upload.apply_async") as mock_task,
        ):
            mock_retry.return_value = ([1, 2, 3], "adminbatch789")

            await admin_retry_uploads(request, user)

            mock_retry.assert_called_once()
            assert mock_task.call_count == 3
            for call in mock_task.call_args_list:
                assert call[1]["args"][1] == "adminbatch789"
                assert call[1]["queue"] == QUEUE_PRIVILEGED

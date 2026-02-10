from unittest.mock import patch

import pytest

from curator.admin import (
    admin_get_batches,
    admin_get_upload_requests,
    admin_get_users,
    admin_retry_uploads,
)
from curator.app.models import RetrySelectedUploadsRequest
from curator.workers.celery import QUEUE_PRIVILEGED


@pytest.mark.asyncio
async def test_admin_get_batches_success(mock_session, patch_get_session):
    patch_get_session("curator.admin.get_session")
    with (
        patch("curator.admin.get_batches") as mock_get_batches,
        patch("curator.admin.count_batches") as mock_count_batches,
    ):
        mock_get_batches.return_value = []
        mock_count_batches.return_value = 0

        result = await admin_get_batches(page=1, limit=100)

        mock_get_batches.assert_called_once_with(mock_session, offset=0, limit=100)
        mock_count_batches.assert_called_once_with(mock_session)
        assert result == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_admin_get_users_success(mock_session, patch_get_session):
    patch_get_session("curator.admin.get_session")
    with (
        patch("curator.admin.get_users") as mock_get_users,
        patch("curator.admin.count_users") as mock_count_users,
    ):
        mock_get_users.return_value = []
        mock_count_users.return_value = 0

        result = await admin_get_users(page=1, limit=100)

        mock_get_users.assert_called_once_with(mock_session, offset=0, limit=100)
        mock_count_users.assert_called_once_with(mock_session)
        assert result == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_admin_get_upload_requests_success(mock_session, patch_get_session):
    patch_get_session("curator.admin.get_session")
    with (
        patch("curator.admin.get_all_upload_requests") as mock_get_all_upload_requests,
        patch(
            "curator.admin.count_all_upload_requests"
        ) as mock_count_all_upload_requests,
    ):
        mock_get_all_upload_requests.return_value = []
        mock_count_all_upload_requests.return_value = 0

        result = await admin_get_upload_requests(page=1, limit=100)

        mock_get_all_upload_requests.assert_called_once_with(
            mock_session, offset=0, limit=100
        )
        mock_count_all_upload_requests.assert_called_once_with(mock_session)
        assert result == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_admin_retry_uploads_success(mock_session, patch_get_session):
    patch_get_session("curator.admin.get_session")
    user = {
        "username": "DaxServer",
        "userid": "u1",
        "access_token": ("token", "secret"),
    }
    request = RetrySelectedUploadsRequest(upload_ids=[1, 2, 3])
    with (
        patch("curator.admin.encrypt_access_token") as mock_encrypt,
        patch("curator.admin.retry_selected_uploads") as mock_retry,
        patch("curator.workers.tasks.process_upload.apply_async") as mock_task,
    ):
        mock_encrypt.return_value = "encrypted_token"
        mock_retry.return_value = [1, 2, 3]

        result = await admin_retry_uploads(request, user)

        mock_encrypt.assert_called_once_with(("token", "secret"))
        mock_retry.assert_called_once_with(
            mock_session, [1, 2, 3], "encrypted_token", "u1"
        )
        assert result == {
            "message": "Retried 3 uploads",
            "retried_count": 3,
            "requested_count": 3,
        }

        # Verify Celery tasks were queued with upload_id, edit_group_id, and privileged queue
        assert mock_task.call_count == 3
        # Check that all calls have the correct structure
        for call in mock_task.call_args_list:
            assert len(call[1]["args"]) == 2  # upload_id and edit_group_id
            assert isinstance(call[1]["args"][0], int)  # upload_id is an integer
            assert isinstance(call[1]["args"][1], str)  # edit_group_id is a string
            assert len(call[1]["args"][1]) == 12  # edit_group_id is 12 characters
            assert (
                call[1]["queue"] == QUEUE_PRIVILEGED
            )  # Admin retries use privileged queue
        # Verify the correct upload_ids were called
        upload_ids = {call[1]["args"][0] for call in mock_task.call_args_list}
        assert upload_ids == {1, 2, 3}


@pytest.mark.asyncio
async def test_admin_retry_uploads_partial(mock_session, patch_get_session):
    """Test admin retry when some uploads are in_progress and skipped"""
    patch_get_session("curator.admin.get_session")
    user = {
        "username": "DaxServer",
        "userid": "u1",
        "access_token": ("token", "secret"),
    }
    # Request 4 uploads, but only 2 are actually retried (others are in_progress)
    request = RetrySelectedUploadsRequest(upload_ids=[1, 2, 3, 4])
    with (
        patch("curator.admin.encrypt_access_token") as mock_encrypt,
        patch("curator.admin.retry_selected_uploads") as mock_retry,
        patch("curator.workers.tasks.process_upload.apply_async") as mock_task,
    ):
        mock_encrypt.return_value = "encrypted_token"
        mock_retry.return_value = [1, 3]  # Only 1 and 3 were retried

        result = await admin_retry_uploads(request, user)

        assert result == {
            "message": "Retried 2 uploads",
            "retried_count": 2,
            "requested_count": 4,
        }

        # Only 2 tasks should be queued
        assert mock_task.call_count == 2
        # Verify both use privileged queue
        for call in mock_task.call_args_list:
            assert call[1]["queue"] == QUEUE_PRIVILEGED


@pytest.mark.asyncio
async def test_admin_retry_uploads_empty_list(mock_session, patch_get_session):
    """Test admin retry with empty upload_ids list"""
    patch_get_session("curator.admin.get_session")
    user = {
        "username": "DaxServer",
        "userid": "u1",
        "access_token": ("token", "secret"),
    }
    request = RetrySelectedUploadsRequest(upload_ids=[])
    with (
        patch("curator.admin.encrypt_access_token") as mock_encrypt,
        patch("curator.admin.retry_selected_uploads") as mock_retry,
        patch("curator.workers.tasks.process_upload.apply_async") as mock_task,
    ):
        mock_encrypt.return_value = "encrypted_token"
        mock_retry.return_value = []

        result = await admin_retry_uploads(request, user)

        assert result == {
            "message": "Retried 0 uploads",
            "retried_count": 0,
            "requested_count": 0,
        }

        # No tasks should be queued
        assert mock_task.call_count == 0

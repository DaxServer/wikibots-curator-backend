from unittest.mock import patch

import pytest
from fastapi import HTTPException

from curator.admin import (
    admin_get_batches,
    admin_get_upload_requests,
    admin_get_users,
    admin_retry_batch,
)


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
async def test_admin_retry_batch_success(mock_session, patch_get_session):
    patch_get_session("curator.admin.get_session")
    user = {
        "username": "DaxServer",
        "userid": "u1",
        "access_token": ("token", "secret"),
    }
    with (
        patch("curator.admin.encrypt_access_token") as mock_encrypt,
        patch("curator.admin.retry_batch_as_admin") as mock_retry,
        patch("curator.workers.tasks.process_upload.delay") as mock_task,
    ):
        mock_encrypt.return_value = "encrypted_token"
        mock_retry.return_value = [1, 2, 3]

        result = await admin_retry_batch(batch_id=1, user=user)

        mock_encrypt.assert_called_once_with(("token", "secret"))
        mock_retry.assert_called_once_with(mock_session, 1, "encrypted_token", "u1")
        assert result == {"message": "Retried 3 uploads"}

        # Verify Celery tasks were queued
        assert mock_task.call_count == 3
        mock_task.assert_any_call(1)
        mock_task.assert_any_call(2)
        mock_task.assert_any_call(3)


@pytest.mark.asyncio
async def test_admin_retry_batch_not_found(mock_session, patch_get_session):
    patch_get_session("curator.admin.get_session")
    user = {
        "username": "DaxServer",
        "userid": "u1",
        "access_token": ("token", "secret"),
    }
    with (
        patch("curator.admin.encrypt_access_token") as mock_encrypt,
        patch("curator.admin.retry_batch_as_admin") as mock_retry,
    ):
        mock_encrypt.return_value = "encrypted_token"
        mock_retry.side_effect = ValueError("Batch not found")

        with pytest.raises(HTTPException) as exc:
            await admin_retry_batch(batch_id=1, user=user)

        assert exc.value.status_code == 404

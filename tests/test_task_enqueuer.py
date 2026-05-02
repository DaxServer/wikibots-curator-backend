"""Tests for task enqueuer queue routing and user queue registration."""

from unittest.mock import MagicMock, patch

import pytest
from mwoauth import AccessToken

from curator.core.rate_limiter import RateLimitInfo


@pytest.fixture
def access_token():
    return AccessToken("key", "secret")


@pytest.fixture
def rate_limit():
    return RateLimitInfo(uploads_per_period=999, period_seconds=1)


@pytest.mark.asyncio
async def test_enqueues_to_user_queue(access_token, rate_limit):
    with (
        patch("curator.core.task_enqueuer.process_upload") as mock_process_upload,
        patch(
            "curator.core.task_enqueuer.get_rate_limit_for_batch",
            return_value=rate_limit,
        ),
        patch("curator.core.task_enqueuer.get_next_upload_delay", return_value=0.0),
        patch("curator.core.task_enqueuer.register_user_queue"),
        patch("curator.core.task_enqueuer.get_session"),
    ):
        mock_process_upload.apply_async.return_value = MagicMock(id="task-1")

        from curator.core.task_enqueuer import enqueue_uploads

        await enqueue_uploads(
            upload_ids=[1],
            edit_group_id="eg1",
            userid="user123",
            access_token=access_token,
        )

        call_kwargs = mock_process_upload.apply_async.call_args[1]
        assert call_kwargs["queue"] == "uploads-user123"


@pytest.mark.asyncio
async def test_calls_register_user_queue(access_token, rate_limit):
    with (
        patch("curator.core.task_enqueuer.process_upload") as mock_process_upload,
        patch(
            "curator.core.task_enqueuer.get_rate_limit_for_batch",
            return_value=rate_limit,
        ),
        patch("curator.core.task_enqueuer.get_next_upload_delay", return_value=0.0),
        patch("curator.core.task_enqueuer.register_user_queue") as mock_register,
        patch("curator.core.task_enqueuer.get_session"),
    ):
        mock_process_upload.apply_async.return_value = MagicMock(id="task-1")

        from curator.core.task_enqueuer import enqueue_uploads

        await enqueue_uploads(
            upload_ids=[1],
            edit_group_id="eg1",
            userid="user123",
            access_token=access_token,
        )

        mock_register.assert_called_once_with("user123")


@pytest.mark.asyncio
async def test_passes_userid_as_task_arg(access_token, rate_limit):
    with (
        patch("curator.core.task_enqueuer.process_upload") as mock_process_upload,
        patch(
            "curator.core.task_enqueuer.get_rate_limit_for_batch",
            return_value=rate_limit,
        ),
        patch("curator.core.task_enqueuer.get_next_upload_delay", return_value=0.0),
        patch("curator.core.task_enqueuer.register_user_queue"),
        patch("curator.core.task_enqueuer.get_session"),
    ):
        mock_process_upload.apply_async.return_value = MagicMock(id="task-1")

        from curator.core.task_enqueuer import enqueue_uploads

        await enqueue_uploads(
            upload_ids=[1],
            edit_group_id="eg1",
            userid="user123",
            access_token=access_token,
        )

        call_kwargs = mock_process_upload.apply_async.call_args[1]
        assert call_kwargs["args"] == [1, "eg1", "user123"]

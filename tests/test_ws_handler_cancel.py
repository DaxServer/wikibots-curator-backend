"""Tests for cancel operation in WebSocket handler."""

from unittest.mock import patch

import pytest

from curator.app.handler import revoke_celery_tasks_by_id
from curator.asyncapi import CancelBatch


@pytest.mark.asyncio
async def test_handle_cancel_batch_success(handler_instance, mock_sender):
    """Test cancel_batch handler successfully cancels queued items with valid task IDs"""
    batch_id = 123

    with (
        patch("curator.app.handler.cancel_batch") as mock_cancel_batch,
        patch("curator.app.handler.revoke_celery_tasks_by_id") as mock_revoke,
    ):
        # Mock cancelled uploads with task IDs
        mock_cancel_batch.return_value = {
            1: "task-1",
            2: "task-2",
            3: "",  # No task ID
        }

        data = CancelBatch(data=batch_id)
        await handler_instance.cancel_batch(data.data)

        # Verify cancel_batch was called
        mock_cancel_batch.assert_called_once()

        # Verify revoke was called with the task IDs
        mock_revoke.assert_called_once_with(
            {
                1: "task-1",
                2: "task-2",
                3: "",
            }
        )

        # Verify no success message sent (relies on subscription for updates)
        mock_sender.send_cancel_batch_ack.assert_not_called()


@pytest.mark.asyncio
async def test_handle_cancel_batch_no_queued_items(handler_instance, mock_sender):
    """Test cancel_batch when no items are queued"""
    batch_id = 123

    with (
        patch("curator.app.handler.cancel_batch") as mock_cancel_batch,
    ):
        # No items to cancel
        mock_cancel_batch.return_value = {}

        data = CancelBatch(data=batch_id)
        await handler_instance.cancel_batch(data.data)

        # Verify error message was sent
        mock_sender.send_error.assert_called_once_with("No queued items to cancel")


@pytest.mark.asyncio
async def test_handle_cancel_batch_not_found(handler_instance, mock_sender):
    """Test cancel_batch when batch doesn't exist"""
    batch_id = 999

    with (
        patch("curator.app.handler.cancel_batch") as mock_cancel_batch,
    ):
        # Batch not found
        mock_cancel_batch.side_effect = ValueError("Batch not found")

        data = CancelBatch(data=batch_id)
        await handler_instance.cancel_batch(data.data)

        # Verify error message was sent (includes batch ID)
        mock_sender.send_error.assert_called_once_with(f"Batch {batch_id} not found")


@pytest.mark.asyncio
async def test_handle_cancel_batch_permission_denied(handler_instance, mock_sender):
    """Test cancel_batch when user doesn't own the batch"""
    batch_id = 123

    with (
        patch("curator.app.handler.cancel_batch") as mock_cancel_batch,
    ):
        # Permission denied
        mock_cancel_batch.side_effect = PermissionError("Permission denied")

        data = CancelBatch(data=batch_id)
        await handler_instance.cancel_batch(data.data)

        # Verify error message was sent
        mock_sender.send_error.assert_called_once_with("Permission denied")


@pytest.mark.asyncio
async def test_revoke_celery_tasks_by_id_all_success():
    """Test revoke_celery_tasks_by_id when all tasks are successfully revoked"""
    upload_task_ids = {
        1: "task-1",
        2: "task-2",
        3: "task-3",
    }

    with patch("curator.app.handler.celery_app.control") as mock_control:
        results = revoke_celery_tasks_by_id(upload_task_ids)

        # Verify revoke was called for each task ID
        assert mock_control.revoke.call_count == 3

        # Verify all results are True (success)
        assert results == {
            1: True,
            2: True,
            3: True,
        }


@pytest.mark.asyncio
async def test_revoke_celery_tasks_by_id_with_missing_task_id():
    """Test revoke_celery_tasks_by_id when some tasks have no task ID"""
    upload_task_ids = {
        1: "task-1",
        2: "",  # No task ID
        3: "task-3",
    }

    with patch("curator.app.handler.celery_app.control") as mock_control:
        results = revoke_celery_tasks_by_id(upload_task_ids)

        # Verify revoke was called only for tasks with IDs
        assert mock_control.revoke.call_count == 2

        # Verify results
        assert results == {
            1: True,
            2: False,  # No task ID
            3: True,
        }


@pytest.mark.asyncio
async def test_revoke_celery_tasks_by_id_with_exception():
    """Test revoke_celery_tasks_by_id when some tasks fail to revoke"""
    upload_task_ids = {
        1: "task-1",
        2: "task-2",
        3: "task-3",
    }

    with patch("curator.app.handler.celery_app.control") as mock_control:
        # Simulate task2 raising an exception
        mock_control.revoke.side_effect = [None, Exception("Task not found"), None]

        results = revoke_celery_tasks_by_id(upload_task_ids)

        # Verify results
        assert results == {
            1: True,
            2: False,
            3: True,
        }

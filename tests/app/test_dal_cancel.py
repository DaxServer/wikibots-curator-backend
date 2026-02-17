"""Tests for batch cancellation operations in data access layer."""

from unittest.mock import MagicMock

import pytest

from curator.app.dal import cancel_batch
from curator.app.models import Batch


def test_cancel_batch_success_queued_items_only(mock_session):
    """Test cancel_batch cancels only queued items in a batch"""
    batch_id = 123
    userid = "user123"

    # Mock batch
    mock_batch = Batch(id=batch_id, userid=userid)
    mock_session.get.return_value = mock_batch

    # Mock queued upload
    mock_upload = MagicMock()
    mock_upload.id = 1
    mock_upload.celery_task_id = "task-1"
    mock_result = MagicMock()
    mock_result.all.return_value = [mock_upload]
    mock_session.exec.return_value = mock_result

    cancelled_uploads = cancel_batch(mock_session, batch_id, userid)

    # Verify only queued item was returned
    assert len(cancelled_uploads) == 1
    assert 1 in cancelled_uploads
    assert cancelled_uploads[1] == "task-1"

    # Verify upload status was updated
    assert mock_upload.status == "cancelled"
    assert mock_session.add.call_count == 1
    mock_session.flush.assert_called_once()


def test_cancel_batch_permission_denied(mock_session):
    """Test cancel_batch raises PermissionError if user doesn't own the batch"""
    batch_id = 123
    owner_userid = "owner123"
    other_userid = "other456"

    # Mock batch owned by different user
    mock_batch = Batch(id=batch_id, userid=owner_userid)
    mock_session.get.return_value = mock_batch

    with pytest.raises(PermissionError, match="Permission denied"):
        cancel_batch(mock_session, batch_id, other_userid)


def test_cancel_batch_not_found(mock_session):
    """Test cancel_batch raises ValueError if batch not found"""
    mock_session.get.return_value = None

    with pytest.raises(ValueError, match="Batch not found"):
        cancel_batch(mock_session, 999, "user123")


def test_cancel_batch_no_queued_items(mock_session):
    """Test cancel_batch returns empty dict when no queued items exist"""
    batch_id = 123
    userid = "user123"

    # Mock batch
    mock_batch = Batch(id=batch_id, userid=userid)
    mock_session.get.return_value = mock_batch

    # No queued items
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_session.exec.return_value = mock_result

    cancelled_uploads = cancel_batch(mock_session, batch_id, userid)

    assert cancelled_uploads == {}


def test_cancel_batch_multiple_queued_items(mock_session):
    """Test cancel_batch cancels all queued items with task IDs"""
    batch_id = 123
    userid = "user123"

    # Mock batch
    mock_batch = Batch(id=batch_id, userid=userid)
    mock_session.get.return_value = mock_batch

    # Multiple queued uploads
    mock_upload1 = MagicMock()
    mock_upload1.id = 1
    mock_upload1.celery_task_id = "task-1"
    mock_upload2 = MagicMock()
    mock_upload2.id = 2
    mock_upload2.celery_task_id = "task-2"
    mock_upload3 = MagicMock()
    mock_upload3.id = 3
    mock_upload3.celery_task_id = None

    mock_result = MagicMock()
    mock_result.all.return_value = [mock_upload1, mock_upload2, mock_upload3]
    mock_session.exec.return_value = mock_result

    cancelled_uploads = cancel_batch(mock_session, batch_id, userid)

    assert len(cancelled_uploads) == 3
    assert 1 in cancelled_uploads
    assert 2 in cancelled_uploads
    assert 3 in cancelled_uploads
    assert cancelled_uploads[1] == "task-1"
    assert cancelled_uploads[2] == "task-2"
    assert cancelled_uploads[3] == ""

    # Verify all uploads were updated
    assert mock_upload1.status == "cancelled"
    assert mock_upload2.status == "cancelled"
    assert mock_upload3.status == "cancelled"
    assert mock_session.add.call_count == 3

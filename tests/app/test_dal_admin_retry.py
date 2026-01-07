import pytest

from curator.app.dal import retry_batch_as_admin
from curator.app.models import Batch, UploadRequest


def test_retry_batch_as_admin_success(mock_session):
    """Test retry_batch_as_admin resets eligible uploads and updates token and last_edited_by"""
    batch_id = 123
    admin_token = "admin_encrypted_token"
    admin_userid = "admin_user"

    # Mock batch
    mock_batch = Batch(id=batch_id, userid="user1")
    mock_session.get.return_value = mock_batch

    # Mock uploads
    # 1. Failed -> should retry
    # 2. Completed -> should retry (requirement: "regardless of their upload items' statuses")
    # 3. In Progress -> should NOT retry
    # 4. Queued -> should retry (update token)

    upload_failed = UploadRequest(
        id=1,
        batchid=batch_id,
        userid="original_user",
        status="failed",
        access_token="old",
        key="1",
        handler="h",
        filename="f1",
        wikitext="w",
    )
    upload_completed = UploadRequest(
        id=2,
        batchid=batch_id,
        userid="original_user",
        status="completed",
        access_token="old",
        key="2",
        handler="h",
        filename="f2",
        wikitext="w",
    )
    upload_inprogress = UploadRequest(
        id=3,
        batchid=batch_id,
        userid="original_user",
        status="in_progress",
        access_token="old",
        key="3",
        handler="h",
        filename="f3",
        wikitext="w",
    )
    upload_queued = UploadRequest(
        id=4,
        batchid=batch_id,
        userid="original_user",
        status="queued",
        access_token="old",
        key="4",
        handler="h",
        filename="f4",
        wikitext="w",
    )

    # Mock exec().all() to return eligible uploads
    # The actual query logic is tested by integration tests or trusting SQLModel,
    # here we mock the result of the query
    mock_session.exec.return_value.all.return_value = [
        upload_failed,
        upload_completed,
        upload_queued,
    ]

    reset_ids = retry_batch_as_admin(mock_session, batch_id, admin_token, admin_userid)

    # Verify results
    assert len(reset_ids) == 3
    assert 1 in reset_ids
    assert 2 in reset_ids
    assert 4 in reset_ids
    assert 3 not in reset_ids

    # Verify updates
    assert upload_failed.status == "queued"
    assert upload_failed.access_token == admin_token
    assert upload_failed.error is None
    assert upload_failed.userid == "original_user"  # Should NOT change
    assert upload_failed.last_edited_by == admin_userid

    assert upload_completed.status == "queued"
    assert upload_completed.access_token == admin_token
    assert upload_completed.userid == "original_user"  # Should NOT change
    assert upload_completed.success is None
    assert upload_completed.last_edited_by == admin_userid

    assert upload_queued.status == "queued"
    assert upload_queued.access_token == admin_token
    assert upload_queued.userid == "original_user"  # Should NOT change
    assert upload_queued.last_edited_by == admin_userid

    assert upload_inprogress.status == "in_progress"
    assert upload_inprogress.access_token == "old"
    assert upload_inprogress.userid == "original_user"
    assert upload_inprogress.last_edited_by is None

    # Verify commit
    mock_session.flush.assert_called_once()


def test_retry_batch_as_admin_batch_not_found(mock_session):
    """Test retry_batch_as_admin raises ValueError if batch not found"""
    mock_session.get.return_value = None

    with pytest.raises(ValueError, match="Batch not found"):
        retry_batch_as_admin(mock_session, 999, "token", "admin")

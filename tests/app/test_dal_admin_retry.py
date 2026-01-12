from curator.app.dal import retry_selected_uploads
from curator.app.models import UploadRequest


def test_retry_selected_uploads_success(mock_session):
    """Test retry_selected_uploads resets eligible uploads and updates token and last_edited_by"""
    upload_ids = [1, 2, 3, 4]
    admin_token = "admin_encrypted_token"
    admin_userid = "admin_user"

    # Mock uploads
    # 1. Failed -> should retry
    # 2. Completed -> should retry
    # 3. In Progress -> should NOT retry
    # 4. Queued -> should retry (update token)

    upload_failed = UploadRequest(
        id=1,
        batchid=123,
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
        batchid=123,
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
        batchid=123,
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
        batchid=123,
        userid="original_user",
        status="queued",
        access_token="old",
        key="4",
        handler="h",
        filename="f4",
        wikitext="w",
    )

    # Mock exec().all() to return all uploads
    mock_session.exec.return_value.all.return_value = [
        upload_failed,
        upload_completed,
        upload_inprogress,
        upload_queued,
    ]

    reset_ids = retry_selected_uploads(
        mock_session, upload_ids, admin_token, admin_userid
    )

    # Verify results - in_progress should be skipped
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

    # in_progress should NOT be modified
    assert upload_inprogress.status == "in_progress"
    assert upload_inprogress.access_token == "old"
    assert upload_inprogress.userid == "original_user"
    assert upload_inprogress.last_edited_by is None

    # Verify commit
    mock_session.flush.assert_called_once()


def test_retry_selected_uploads_empty_list(mock_session):
    """Test retry_selected_uploads with empty upload_ids list"""
    reset_ids = retry_selected_uploads(mock_session, [], "token", "admin")
    assert reset_ids == []
    mock_session.exec.assert_not_called()


def test_retry_selected_uploads_nonexistent_ids(mock_session):
    """Test retry_selected_uploads silently ignores non-existent IDs"""
    upload_ids = [1, 999, 1000]  # 999 and 1000 don't exist
    admin_token = "admin_encrypted_token"
    admin_userid = "admin_user"

    upload_1 = UploadRequest(
        id=1,
        batchid=123,
        userid="user",
        status="failed",
        access_token="old",
        key="1",
        handler="h",
        filename="f1",
        wikitext="w",
    )

    # Mock exec().all() to return only ID 1 (others don't exist)
    mock_session.exec.return_value.all.return_value = [upload_1]

    reset_ids = retry_selected_uploads(
        mock_session, upload_ids, admin_token, admin_userid
    )

    # Only ID 1 should be reset
    assert len(reset_ids) == 1
    assert 1 in reset_ids

    assert upload_1.status == "queued"
    assert upload_1.access_token == admin_token
    assert upload_1.last_edited_by == admin_userid


def test_retry_selected_uploads_all_in_progress(mock_session):
    """Test retry_selected_uploads when all uploads are in_progress"""
    upload_ids = [1, 2]
    admin_token = "admin_encrypted_token"
    admin_userid = "admin_user"

    upload_1 = UploadRequest(
        id=1,
        batchid=123,
        userid="user",
        status="in_progress",
        access_token="old",
        key="1",
        handler="h",
        filename="f1",
        wikitext="w",
    )
    upload_2 = UploadRequest(
        id=2,
        batchid=123,
        userid="user",
        status="in_progress",
        access_token="old",
        key="2",
        handler="h",
        filename="f2",
        wikitext="w",
    )

    mock_session.exec.return_value.all.return_value = [upload_1, upload_2]

    reset_ids = retry_selected_uploads(
        mock_session, upload_ids, admin_token, admin_userid
    )

    # None should be reset
    assert len(reset_ids) == 0

    # Verify uploads were not modified
    assert upload_1.status == "in_progress"
    assert upload_1.access_token == "old"
    assert upload_1.last_edited_by is None

    assert upload_2.status == "in_progress"
    assert upload_2.access_token == "old"
    assert upload_2.last_edited_by is None

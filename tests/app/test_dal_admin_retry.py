from curator.app.dal import retry_selected_uploads
from curator.app.models import UploadRequest


def _make_upload_request(
    upload_id: int,
    status: str,
    batchid: int = 123,
    userid: str = "original_user",
) -> UploadRequest:
    """Helper to create UploadRequest for testing"""
    return UploadRequest(
        id=upload_id,
        batchid=batchid,
        userid=userid,
        status=status,
        access_token="old",
        key=str(upload_id),
        handler="h",
        filename=f"f{upload_id}",
        wikitext="w",
    )


def test_retry_selected_uploads_success(mock_session):
    """Test retry_selected_uploads resets eligible uploads and updates token and last_edited_by"""
    upload_ids = [1, 2, 3, 4]
    admin_token = "admin_encrypted_token"
    admin_userid = "admin_user"

    mock_session.exec.return_value.all.return_value = [
        _make_upload_request(1, "failed"),
        _make_upload_request(2, "completed"),
        _make_upload_request(3, "in_progress"),
        _make_upload_request(4, "queued"),
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

    # Verify exec was called twice (select and update)
    assert mock_session.exec.call_count == 2

    # Verify flush was called
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

    mock_session.exec.return_value.all.return_value = [
        _make_upload_request(1, "failed", userid="user")
    ]

    reset_ids = retry_selected_uploads(
        mock_session, upload_ids, admin_token, admin_userid
    )

    # Only ID 1 should be reset
    assert len(reset_ids) == 1
    assert 1 in reset_ids


def test_retry_selected_uploads_all_in_progress(mock_session):
    """Test retry_selected_uploads when all uploads are in_progress"""
    upload_ids = [1, 2]
    admin_token = "admin_encrypted_token"
    admin_userid = "admin_user"

    upload_1 = _make_upload_request(1, "in_progress", userid="user")
    upload_2 = _make_upload_request(2, "in_progress", userid="user")
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

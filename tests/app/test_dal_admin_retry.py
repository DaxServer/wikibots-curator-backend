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

    # Mock returns tuples of (id,) for non-in_progress uploads
    mock_session.exec.return_value.all.return_value = [
        (1,),  # failed
        (2,),  # completed
        (4,),  # queued
        # 3 is in_progress and should be skipped
    ]

    reset_ids = retry_selected_uploads(
        mock_session, upload_ids, admin_token, admin_userid
    )

    # Only non-in_progress uploads should be reset (as tuples)
    assert len(reset_ids) == 3
    assert (1,) in reset_ids
    assert (2,) in reset_ids
    assert (4,) in reset_ids
    assert (3,) not in reset_ids

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

    # Mock returns tuple for non-in_progress upload
    mock_session.exec.return_value.all.return_value = [
        (1,),  # Upload 1 is not in_progress
    ]

    reset_ids = retry_selected_uploads(
        mock_session, upload_ids, admin_token, admin_userid
    )

    # Only ID 1 should be reset (as tuple)
    assert len(reset_ids) == 1
    assert (1,) in reset_ids


def test_retry_selected_uploads_all_in_progress(mock_session):
    """Test retry_selected_uploads when all uploads are in_progress"""
    upload_ids = [1, 2]
    admin_token = "admin_encrypted_token"
    admin_userid = "admin_user"

    # Mock returns empty list (all uploads are in_progress)
    mock_session.exec.return_value.all.return_value = []

    reset_ids = retry_selected_uploads(
        mock_session, upload_ids, admin_token, admin_userid
    )

    # None should be reset
    assert len(reset_ids) == 0

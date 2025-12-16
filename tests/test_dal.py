from unittest.mock import Mock

from curator.app.dal import get_upload_request_by_id
from curator.app.models import UploadRequest


def test_get_upload_request_by_id():
    """Test that get_upload_request_by_id works with integer ID"""
    # Create a mock session
    mock_session = Mock()

    # Create a mock UploadRequest
    mock_upload_request = Mock(spec=UploadRequest)
    mock_upload_request.id = 123

    # Configure the mock session.get to return our mock upload request
    mock_session.get.return_value = mock_upload_request

    # Test the function
    result = get_upload_request_by_id(mock_session, 123)

    # Verify the session.get was called with the correct arguments
    mock_session.get.assert_called_once_with(UploadRequest, 123)

    # Verify the result
    assert result == mock_upload_request


def test_get_upload_request_by_id_not_found():
    """Test that get_upload_request_by_id returns None when not found"""
    # Create a mock session
    mock_session = Mock()

    # Configure the mock session.get to return None
    mock_session.get.return_value = None

    # Test the function
    result = get_upload_request_by_id(mock_session, 456)

    # Verify the session.get was called with the correct arguments
    mock_session.get.assert_called_once_with(UploadRequest, 456)

    # Verify the result
    assert result is None


def test_get_upload_request_by_id_with_wrong_type():
    """Test that get_upload_request_by_id returns None when passed invalid input (fixed behavior)"""
    # Create a mock session
    mock_session = Mock()

    # Test the function with a dictionary (should return None due to input validation)
    result = get_upload_request_by_id(mock_session, {"id": 123, "key": "test"})

    # Verify the result is None (input validation should prevent session.get call)
    assert result is None

    # Verify session.get was NOT called due to input validation
    mock_session.get.assert_not_called()


def test_reset_failed_uploads_success():
    mock_session = Mock()
    mock_batch = Mock()
    mock_batch.userid = "user1"
    mock_session.get.return_value = mock_batch

    mock_upload1 = Mock(spec=UploadRequest)
    mock_upload1.id = 1
    mock_upload1.status = "failed"
    mock_upload1.error = "some error"
    mock_upload1.result = "some result"

    mock_upload2 = Mock(spec=UploadRequest)
    mock_upload2.id = 2
    mock_upload2.status = "failed"

    mock_session.exec.return_value.all.return_value = [mock_upload1, mock_upload2]

    from curator.app.dal import reset_failed_uploads

    result = reset_failed_uploads(mock_session, 123, "user1", "encrypted_token")

    assert len(result) == 2
    assert result == [1, 2]
    assert mock_upload1.status == "queued"
    assert mock_upload1.error is None
    assert mock_upload1.result is None
    assert mock_upload1.access_token == "encrypted_token"
    assert mock_upload2.status == "queued"
    assert mock_upload2.access_token == "encrypted_token"
    mock_session.commit.assert_called_once()


def test_reset_failed_uploads_not_found():
    mock_session = Mock()
    mock_session.get.return_value = None

    import pytest

    from curator.app.dal import reset_failed_uploads

    with pytest.raises(ValueError, match="Batch not found"):
        reset_failed_uploads(mock_session, 123, "user1", "encrypted_token")


def test_reset_failed_uploads_forbidden():
    mock_session = Mock()
    mock_batch = Mock()
    mock_batch.userid = "other_user"
    mock_session.get.return_value = mock_batch

    import pytest

    from curator.app.dal import reset_failed_uploads

    with pytest.raises(PermissionError, match="Permission denied"):
        reset_failed_uploads(mock_session, 123, "user1", "encrypted_token")

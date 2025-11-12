import pytest
from unittest.mock import Mock
from curator.app.models import UploadRequest
from curator.app.dal import get_upload_request_by_id


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

from unittest.mock import Mock, patch

from curator.app.dal import update_upload_status
from curator.app.models import DuplicateError, GenericError, UploadRequest


def test_upload_request_model_validation():
    """Test that UploadRequest model accepts structured error data."""
    error_data: DuplicateError = {
        "type": "duplicate",
        "message": "File already exists",
        "links": [{"title": "Existing File", "url": "http://example.com"}],
    }

    req = UploadRequest(
        userid="testuser",
        status="failed",
        key="image1",
        handler="mapillary",
        filename="test.jpg",
        error=error_data,
    )

    assert req.error == error_data
    assert req.error is not None
    assert req.error["type"] == "duplicate"


@patch("curator.app.dal.update")
def test_update_upload_status_with_error(mock_update):
    """Test update_upload_status calls session.exec with correct update statement."""
    mock_session = Mock()

    error_data: GenericError = {"type": "error", "message": "Something went wrong"}

    # Setup the mock update chain
    # update(UploadRequest) -> .where(...) -> .values(...)
    mock_update_stmt = Mock()
    mock_where_clause = Mock()
    mock_values_clause = Mock()

    mock_update.return_value = mock_update_stmt
    mock_update_stmt.where.return_value = mock_where_clause
    mock_where_clause.values.return_value = mock_values_clause

    upload_id = 123

    update_upload_status(
        session=mock_session, upload_id=upload_id, status="failed", error=error_data
    )

    # Verify update was called with correct model
    mock_update.assert_called_once_with(UploadRequest)

    # Verify where was called
    mock_update_stmt.where.assert_called_once()

    # Verify values was called with correct dict
    mock_where_clause.values.assert_called_once()
    call_kwargs = mock_where_clause.values.call_args.kwargs

    assert call_kwargs["status"] == "failed"
    assert call_kwargs["error"] == error_data

    # Verify session.exec was called with the result of values()
    mock_session.exec.assert_called_once_with(mock_values_clause)
    mock_session.commit.assert_called_once()

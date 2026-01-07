from unittest.mock import Mock, patch

from curator.app.dal import update_upload_status
from curator.app.models import UploadRequest
from curator.asyncapi import (
    DuplicateError,
    ErrorLink,
    GenericError,
    TitleBlacklistedError,
)


def test_upload_request_model_validation():
    """Test that UploadRequest model accepts structured error data."""
    error_data = DuplicateError(
        message="File already exists",
        links=[ErrorLink(title="Existing File", url="http://example.com")],
    )

    req = UploadRequest(
        userid="testuser",
        status="failed",
        key="image1",
        handler="mapillary",
        filename="test.jpg",
        error=error_data,
        wikitext="wikitext",
    )

    # In SQLModel with JSON column, the data is returned as a dict if passed as a dict
    assert req.error is not None
    assert isinstance(req.error, DuplicateError)
    assert req.error.type == "duplicate"
    assert req.error.message == "File already exists"
    assert len(req.error.links) == 1
    assert req.error.links[0].title == "Existing File"
    assert req.error.links[0].url == "http://example.com"


def test_upload_request_model_validation_generic_error():
    """Test that UploadRequest model accepts GenericError structured error data."""
    error_data = GenericError(message="Something went wrong")

    req = UploadRequest(
        userid="testuser",
        status="failed",
        key="image1",
        handler="mapillary",
        filename="test.jpg",
        error=error_data,
        wikitext="wikitext",
    )

    assert req.error is not None
    assert isinstance(req.error, GenericError)
    assert req.error.type == "error"
    assert req.error.message == "Something went wrong"


def test_upload_request_model_validation_title_blacklisted_error():
    """Test that UploadRequest model accepts TitleBlacklistedError structured error data."""
    error_data = TitleBlacklistedError(message="Title contains blacklisted pattern")

    req = UploadRequest(
        userid="testuser",
        status="failed",
        key="image1",
        handler="mapillary",
        filename="test.jpg",
        error=error_data,
        wikitext="wikitext",
    )

    assert req.error is not None
    assert isinstance(req.error, TitleBlacklistedError)
    assert req.error.type == "title_blacklisted"
    assert req.error.message == "Title contains blacklisted pattern"


@patch("curator.app.dal.update")
def test_update_upload_status_with_error(mock_update, mock_session):
    """Test update_upload_status calls session.exec with correct update statement."""
    error_model = GenericError(message="Something went wrong")

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
        session=mock_session, upload_id=upload_id, status="failed", error=error_model
    )

    # Verify update was called with correct model
    mock_update.assert_called_once_with(UploadRequest)

    # Verify where was called
    mock_update_stmt.where.assert_called_once()

    # Verify values was called with correct dict
    mock_where_clause.values.assert_called_once()
    call_kwargs = mock_where_clause.values.call_args.kwargs

    assert call_kwargs["status"] == "failed"
    # Should be converted to dict
    assert call_kwargs["error"] == error_model.model_dump(
        mode="json", exclude_none=True
    )

    # Verify session.exec was called with the result of values()
    mock_session.exec.assert_called_once_with(mock_values_clause)
    mock_session.flush.assert_called_once()


@patch("curator.app.dal.update")
def test_update_upload_status_with_duplicate_error(mock_update, mock_session):
    """Test update_upload_status with DuplicateError."""
    error_model = DuplicateError(
        message="File already exists",
        links=[ErrorLink(title="Existing File", url="http://example.com")],
    )

    # Setup the mock update chain
    mock_update_stmt = Mock()
    mock_where_clause = Mock()
    mock_values_clause = Mock()

    mock_update.return_value = mock_update_stmt
    mock_update_stmt.where.return_value = mock_where_clause
    mock_where_clause.values.return_value = mock_values_clause

    upload_id = 456

    update_upload_status(
        session=mock_session, upload_id=upload_id, status="failed", error=error_model
    )

    # Verify update was called with correct model
    mock_update.assert_called_once_with(UploadRequest)

    # Verify where was called
    mock_update_stmt.where.assert_called_once()

    # Verify values was called with correct dict
    mock_where_clause.values.assert_called_once()
    call_kwargs = mock_where_clause.values.call_args.kwargs

    assert call_kwargs["status"] == "failed"
    # Should be converted to dict
    assert call_kwargs["error"] == error_model.model_dump(
        mode="json", exclude_none=True
    )

    # Verify session.exec was called with the result of values()
    mock_session.exec.assert_called_once_with(mock_values_clause)
    mock_session.flush.assert_called_once()


@patch("curator.app.dal.update")
def test_update_upload_status_with_title_blacklisted_error(mock_update, mock_session):
    """Test update_upload_status with TitleBlacklistedError."""
    error_model = TitleBlacklistedError(message="Title contains blacklisted pattern")

    # Setup the mock update chain
    mock_update_stmt = Mock()
    mock_where_clause = Mock()
    mock_values_clause = Mock()

    mock_update.return_value = mock_update_stmt
    mock_update_stmt.where.return_value = mock_where_clause
    mock_where_clause.values.return_value = mock_values_clause

    upload_id = 789

    update_upload_status(
        session=mock_session, upload_id=upload_id, status="failed", error=error_model
    )

    # Verify update was called with correct model
    mock_update.assert_called_once_with(UploadRequest)

    # Verify where was called
    mock_update_stmt.where.assert_called_once()

    # Verify values was called with correct dict
    mock_where_clause.values.assert_called_once()
    call_kwargs = mock_where_clause.values.call_args.kwargs

    assert call_kwargs["status"] == "failed"
    # Should be converted to dict
    assert call_kwargs["error"] == error_model.model_dump(
        mode="json", exclude_none=True
    )

    # Verify session.exec was called with the result of values()
    mock_session.exec.assert_called_once_with(mock_values_clause)
    mock_session.flush.assert_called_once()

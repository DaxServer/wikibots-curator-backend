import pytest
from unittest.mock import MagicMock
from curator.app.dal import get_upload_request


def test_get_upload_request_with_last_editor(mock_session):
    # Mock UploadRequest
    mock_req = MagicMock()
    mock_req.id = 1
    # last_edited_by column is the ID
    mock_req.last_edited_by = "admin_user_id"

    # Mock last_editor relationship (User object)
    mock_editor = MagicMock()
    mock_editor.username = "admin_username"
    mock_req.last_editor = mock_editor

    # Other fields required by BatchUploadItem
    mock_req.status = "queued"
    mock_req.filename = "file"
    mock_req.wikitext = "wiki"
    mock_req.batchid = 100
    mock_req.userid = "user"
    mock_req.key = "key"
    mock_req.handler = "handler"
    mock_req.labels = None
    mock_req.result = None
    mock_req.error = None
    mock_req.success = None
    mock_req.created_at = None
    mock_req.updated_at = None

    # Mock the query result
    mock_session.exec.return_value.all.return_value = [mock_req]

    # Execute
    result = get_upload_request(mock_session, 100)

    # Verify
    assert len(result) == 1
    # Check that last_edited_by field in result (BatchUploadItem) is the username
    assert result[0].last_edited_by == "admin_username"


def test_get_upload_request_without_last_editor(mock_session):
    # Mock UploadRequest
    mock_req = MagicMock()
    mock_req.id = 2
    mock_req.last_edited_by = None
    mock_req.last_editor = None

    # Other fields
    mock_req.status = "queued"
    mock_req.filename = "file"
    mock_req.wikitext = "wiki"
    mock_req.batchid = 100
    mock_req.userid = "user"
    mock_req.key = "key"
    mock_req.handler = "handler"
    mock_req.labels = None
    mock_req.result = None
    mock_req.error = None
    mock_req.success = None
    mock_req.created_at = None
    mock_req.updated_at = None

    mock_session.exec.return_value.all.return_value = [mock_req]

    result = get_upload_request(mock_session, 100)

    assert len(result) == 1
    assert result[0].last_edited_by is None

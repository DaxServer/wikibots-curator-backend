"""Tests for fetching upload requests from database."""

from unittest.mock import MagicMock

from curator.db.dal_uploads import get_upload_request


def test_get_upload_request(mock_session):
    mock_req = MagicMock()
    mock_req.id = 1
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
    assert result[0].id == 1

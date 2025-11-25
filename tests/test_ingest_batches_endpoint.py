import pytest
import asyncio
from unittest.mock import Mock, patch
from fastapi import HTTPException
from curator.ingest import get_user_batches, get_uploads_by_batch


# Helper to run async functions in sync tests
def run_async(coro):
    return asyncio.run(coro)


@pytest.fixture
def mock_request():
    req = Mock()
    # Simulate a session dict with a user sub (userid)
    req.session = {"user": {"sub": "user123"}}
    return req


def test_get_user_batches_success(mock_request):
    # Prepare mock batch objects
    batch1 = Mock()
    batch1.batch_uid = "batch-1"
    batch1.created_at = "2025-11-01T12:00:00Z"
    batch2 = Mock()
    batch2.batch_uid = "batch-2"
    batch2.created_at = "2025-11-02T12:00:00Z"
    mock_batches = [batch1, batch2]

    mock_session = Mock()

    # Patch DAL functions
    with (
        patch(
            "curator.ingest.get_batches", return_value=mock_batches
        ) as mock_get_batches,
        patch("curator.ingest.count_batches", return_value=2) as mock_count_batches,
    ):
        result = run_async(
            get_user_batches(mock_request, page=1, limit=100, session=mock_session)
        )

    # Verify DAL calls
    mock_get_batches.assert_called_once_with(
        mock_session, userid="user123", offset=0, limit=100
    )
    mock_count_batches.assert_called_once_with(mock_session, userid="user123")

    # Verify response structure
    assert "items" in result
    assert "total" in result
    assert result["total"] == 2
    assert len(result["items"]) == 2
    assert result["items"][0]["batch_uid"] == "batch-1"
    assert result["items"][0]["created_at"] == "2025-11-01T12:00:00Z"


def test_get_user_batches_pagination(mock_request):
    batch = Mock()
    batch.batch_uid = "batch-1"
    batch.created_at = "2025-11-01T12:00:00Z"

    mock_session = Mock()

    with (
        patch("curator.ingest.get_batches", return_value=[batch]) as mock_get_batches,
        patch("curator.ingest.count_batches", return_value=1) as mock_count_batches,
    ):
        result = run_async(
            get_user_batches(mock_request, page=2, limit=50, session=mock_session)
        )

    mock_get_batches.assert_called_once_with(
        mock_session, userid="user123", offset=50, limit=50
    )
    mock_count_batches.assert_called_once_with(mock_session, userid="user123")
    assert result["total"] == 1
    assert len(result["items"]) == 1


def test_get_user_batches_unauthorized():
    # Request without userid in session should raise HTTPException 401
    req = Mock()
    req.session = {"user": {}}
    mock_session = Mock()
    with pytest.raises(HTTPException) as exc_info:
        run_async(get_user_batches(req, page=1, limit=100, session=mock_session))
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unauthorized"


# ---------- Tests for get_uploads_by_batch ----------


@pytest.fixture
def mock_request_with_user():
    req = Mock()
    req.session = {"user": {"sub": "user123"}}
    return req


def test_get_uploads_by_batch_success(mock_request_with_user):
    # Prepare mock upload request objects
    upload1 = Mock()
    upload1.id = "req-1"
    upload1.status = "completed"
    upload1.key = "image1"
    upload1.batch_id = "batch-1"
    upload1.result = {"some": "result"}
    upload1.error = None
    upload1.success = True
    upload1.handler = "mapillary"

    upload2 = Mock()
    upload2.id = "req-2"
    upload2.status = "failed"
    upload2.key = "image2"
    upload2.batch_id = "batch-1"
    upload2.result = None
    upload2.error = '{"msg": "something went wrong"}'
    upload2.success = False
    upload2.handler = "flickr"

    mock_items = [upload1, upload2]
    mock_session = Mock()

    with (
        patch(
            "curator.ingest.get_upload_request", return_value=mock_items
        ) as mock_get_uploads,
        patch("curator.ingest.count_uploads_in_batch", return_value=2) as mock_count,
    ):
        result = run_async(
            get_uploads_by_batch(
                mock_request_with_user,
                batch_id="batch-1",
                page=1,
                limit=100,
                session=mock_session,
            )
        )

    mock_get_uploads.assert_called_once_with(
        mock_session, userid="user123", batch_id="batch-1", offset=0, limit=100
    )
    mock_count.assert_called_once_with(
        mock_session, userid="user123", batch_id="batch-1"
    )

    assert "items" in result
    assert "total" in result
    assert result["total"] == 2
    assert len(result["items"]) == 2
    first = result["items"][0]
    assert first["id"] == "req-1"
    assert first["status"] == "completed"
    assert first["image_id"] == "image1"
    assert first["batch_id"] == "batch-1"
    assert first["result"] == {"some": "result"}
    assert first["error"] is None
    assert first["success"] is True
    assert first["handler"] == "mapillary"

    second = result["items"][1]
    assert second["error"] == {"msg": "something went wrong"}


def test_get_uploads_by_batch_pagination(mock_request_with_user):
    upload = Mock()
    upload.id = "req-1"
    upload.status = "completed"
    upload.key = "image1"
    upload.batch_id = "batch-1"
    upload.result = None
    upload.error = None
    upload.success = True
    upload.handler = "mapillary"

    mock_session = Mock()

    with (
        patch(
            "curator.ingest.get_upload_request", return_value=[upload]
        ) as mock_get_uploads,
        patch("curator.ingest.count_uploads_in_batch", return_value=1) as mock_count,
    ):
        result = run_async(
            get_uploads_by_batch(
                mock_request_with_user,
                batch_id="batch-1",
                page=3,
                limit=25,
                session=mock_session,
            )
        )

    mock_get_uploads.assert_called_once_with(
        mock_session, userid="user123", batch_id="batch-1", offset=50, limit=25
    )
    mock_count.assert_called_once_with(
        mock_session, userid="user123", batch_id="batch-1"
    )
    assert result["total"] == 1
    assert len(result["items"]) == 1


def test_get_uploads_by_batch_unauthorized():
    req = Mock()
    req.session = {"user": {}}
    mock_session = Mock()
    with pytest.raises(HTTPException) as exc_info:
        run_async(
            get_uploads_by_batch(
                req, batch_id="batch-1", page=1, limit=100, session=mock_session
            )
        )
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unauthorized"

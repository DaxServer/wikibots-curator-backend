import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet
from fastapi import Request, status
from fastapi.exceptions import HTTPException

from curator.asyncapi import Creator, Dates, GeoLocation, MediaImage
from curator.asyncapi.GenericError import GenericError

# Set up encryption key for tests
if not os.environ.get("TOKEN_ENCRYPTION_KEY"):
    os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()


# Common Mock Fixtures
@pytest.fixture
def mock_session():
    """Standard mock database session"""
    session = MagicMock()
    session.refresh = MagicMock()
    session.get.return_value = None
    session.exec.return_value.all.return_value = []
    session.exec.return_value.first.return_value = None
    return session


@pytest.fixture
def mock_user():
    """Standard mock user data"""
    return {
        "username": "testuser",
        "userid": "user123",
        "access_token": "test_token",
    }


@pytest.fixture
def mock_request(mock_user):
    """Standard mock FastAPI request with user session"""
    request = MagicMock(spec=Request)
    request.session = {
        "user": mock_user,
        "access_token": mock_user["access_token"],
    }
    return request


@pytest.fixture
def mock_upload_request():
    """Standard mock upload request object"""
    upload = MagicMock()
    upload.id = 1
    upload.batchid = 123
    upload.userid = "user123"
    upload.key = "img-1"
    upload.filename = "Test.jpg"
    upload.wikitext = "== Summary =="
    upload.sdc = [{"P180": "Q42"}]
    upload.labels = {"en": "Test"}
    upload.collection = "seq-1"
    upload.access_token = "cipher"
    upload.status = "queued"
    upload.user.username = "testuser"
    upload.error = None
    upload.result = None
    return upload


@pytest.fixture
def mock_batch():
    """Standard mock batch object"""
    batch = MagicMock()
    batch.id = 123
    batch.userid = "user123"
    batch.name = "Test Batch"
    batch.description = "Test Description"
    return batch


@pytest.fixture
def mock_image():
    """Standard mock image object"""
    return MediaImage(
        id="img-1",
        title="Test Image",
        dates=Dates(taken="2023-01-01T00:00:00Z"),
        creator=Creator(
            id="u1", username="user1", profile_url="https://example.com/u1"
        ),
        location=GeoLocation(latitude=0.0, longitude=0.0, compass_angle=0.0),
        existing=[],
        url_original="https://example.com/file.jpg",
        thumbnail_url="https://example.com/thumb.jpg",
        preview_url="https://example.com/preview.jpg",
        url="https://example.com/photo",
        width=100,
        height=100,
    )


@pytest.fixture
def mock_handler_instance(mock_image):
    """Standard mock MapillaryHandler instance"""
    handler = MagicMock()
    handler.fetch_image_metadata = AsyncMock(return_value=mock_image)
    return handler


@pytest.fixture
def mock_redis():
    """Standard mock Redis client"""
    redis = MagicMock()
    redis.get.return_value = None
    redis.set.return_value = True
    redis.delete.return_value = True
    return redis


@pytest.fixture
def mock_requests_response():
    """Standard mock HTTP response"""
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    response.json.return_value = {}
    response.content = b"test content"
    response.raise_for_status.return_value = None
    return response


@pytest.fixture
def mock_websocket_sender():
    """Standard mock WebSocket sender"""
    sender = MagicMock()
    sender.send_batches_list = AsyncMock()
    sender.send_batch_items = AsyncMock()
    sender.send_error = AsyncMock()
    return sender


# Common Patch Fixtures


@pytest.fixture
def mock_get(mocker):
    """Standard mock HTTP GET request"""
    return mocker.patch("httpx.get")


@pytest.fixture
def patch_get_session(mocker, mock_session):
    """Patch get_session to return mock session"""
    return mocker.patch(
        "curator.workers.ingest.get_session", return_value=iter([mock_session])
    )


@pytest.fixture
def patch_handler_optimized_get_session(mocker, mock_session):
    """Patch get_session for handler_optimized tests to return mock session"""
    return mocker.patch(
        "curator.app.handler_optimized.get_session", return_value=iter([mock_session])
    )


@pytest.fixture
def patch_get_upload_request_by_id(mocker, mock_upload_request):
    """Patch get_upload_request_by_id to return mock upload request"""
    return mocker.patch(
        "curator.workers.ingest.get_upload_request_by_id",
        return_value=mock_upload_request,
    )


@pytest.fixture
def patch_mapillary_handler(mocker, mock_handler_instance):
    """Patch MapillaryHandler to return mock instance"""
    return mocker.patch(
        "curator.workers.ingest.MapillaryHandler", return_value=mock_handler_instance
    )


@pytest.fixture
def patch_decrypt_access_token(mocker):
    """Patch decrypt_access_token to return test tokens"""
    return mocker.patch(
        "curator.workers.ingest.decrypt_access_token", return_value=("token", "secret")
    )


@pytest.fixture
def patch_check_title_blacklisted(mocker):
    """Patch check_title_blacklisted to return not blacklisted"""
    return mocker.patch(
        "curator.workers.ingest.check_title_blacklisted", return_value=(False, "")
    )


@pytest.fixture
def patch_upload_file_chunked(mocker):
    """Patch upload_file_chunked to return success"""
    return mocker.patch(
        "curator.workers.ingest.upload_file_chunked",
        return_value={"url": "https://commons.wikimedia.org/wiki/File:Test.jpg"},
    )


@pytest.fixture
def patch_update_upload_status(mocker):
    """Patch update_upload_status"""
    return mocker.patch("curator.workers.ingest.update_upload_status")


@pytest.fixture
def patch_clear_upload_access_token(mocker):
    """Patch clear_upload_access_token"""
    return mocker.patch("curator.workers.ingest.clear_upload_access_token")


# Common Test Data Fixtures
@pytest.fixture
def test_sdc_data():
    """Standard SDC data for testing"""
    return [{"P180": "Q42"}]


@pytest.fixture
def test_labels_data():
    """Standard labels data for testing"""
    return {"en": "Test Label"}


@pytest.fixture
def test_wikitext():
    """Standard wikitext for testing"""
    return "== Summary ==\n{{Information\n|Description=Test Description\n|Source=Test Source\n}}"


@pytest.fixture
def test_batch_stats():
    """Standard batch stats for testing"""
    return {
        "total": 10,
        "completed": 5,
        "failed": 2,
        "queued": 3,
        "in_progress": 0,
    }


# Error Response Fixtures
@pytest.fixture
def generic_error():
    """Standard generic error"""
    return GenericError(type="error", message="Test error message")


@pytest.fixture
def http_exception():
    """Standard HTTP exception"""
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Test error")

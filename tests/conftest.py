import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet
from fastapi import Request, status
from fastapi.exceptions import HTTPException
from mwoauth import AccessToken

from curator.asyncapi import (
    CameraInfo,
    Creator,
    Dates,
    GeoLocation,
    ImageDimensions,
    ImageUrls,
    MediaImage,
)
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
def mock_get_session(mock_session):
    """Fixture that mocks the get_session context manager"""
    from contextlib import contextmanager

    @contextmanager
    def _mock_get_session():
        try:
            yield mock_session
        finally:
            mock_session.close()

    return _mock_get_session


@pytest.fixture
def mock_user():
    """Standard mock user data"""
    return {
        "username": "testuser",
        "userid": "user123",
        "access_token": AccessToken("test_token", "test_secret"),
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
    return batch


@pytest.fixture
def mock_isolated_site():
    """Mock isolated site with async run support"""
    mock_site = AsyncMock()
    # has_group is synchronous in real code, but mock it appropriately
    mock_site.has_group = MagicMock(return_value=False)

    async def run_side_effect(func, *args, **kwargs):
        # We need to inject a mock site object if the function expects 'site'
        # The real IsolatedSite.run passes a pywikibot.Site object
        # Here we just pass an AsyncMock or MagicMock
        res = func(AsyncMock(), *args, **kwargs)
        if asyncio.iscoroutine(res):
            return await res
        return res

    mock_site.run.side_effect = run_side_effect
    return mock_site


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
        location=GeoLocation(latitude=0.0, longitude=0.0),
        urls=ImageUrls(
            url="https://example.com/photo",
            original="https://example.com/file.jpg",
            preview="https://example.com/preview.jpg",
            thumbnail="https://example.com/thumb.jpg",
        ),
        dimensions=ImageDimensions(width=100, height=100),
        camera=CameraInfo(make="Canon", model="EOS 5D", is_pano=False),
        existing=[],
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


@pytest.fixture(autouse=True)
def mock_commons_functions(mocker):
    """Auto-mock commons.py functions that make Pywikibot API calls"""
    mock_site = MagicMock()
    mock_site.has_group = MagicMock(return_value=False)
    mocker.patch("curator.app.commons.create_isolated_site", return_value=mock_site)


@pytest.fixture
def mock_sender():
    """Comprehensive mock WebSocket sender covering all AsyncAPI messages"""
    sender = MagicMock()
    sender.send_batches_list = AsyncMock()
    sender.send_batch_items = AsyncMock()
    sender.send_batch_uploads_list = AsyncMock()
    sender.send_collection_images = AsyncMock()
    sender.send_upload_created = AsyncMock()
    sender.send_subscribed = AsyncMock()
    sender.send_uploads_update = AsyncMock()
    sender.send_uploads_complete = AsyncMock()
    sender.send_upload_slice_ack = AsyncMock()
    sender.send_batch_created = AsyncMock()
    sender.send_cancel_batch_ack = AsyncMock()
    sender.send_error = AsyncMock()
    return sender


@pytest.fixture
def handler_instance(mocker, mock_user, mock_sender, patch_get_session):
    """Standardized Handler instance with get_session pre-patched"""
    from curator.app.handler import Handler

    patch_get_session("curator.app.handler.get_session")
    return Handler(mock_user, mock_sender, mocker.MagicMock())


# Common Patch Fixtures


@pytest.fixture
def mock_get(mocker):
    """Standard mock HTTP GET request"""
    return mocker.patch("httpx.get")


@pytest.fixture
def patch_get_session(mocker, mock_get_session):
    """Generic fixture to patch get_session in a specified target"""

    def _patch(target):
        return mocker.patch(target, side_effect=mock_get_session)

    return _patch


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
        "curator.workers.ingest.decrypt_access_token",
        return_value=AccessToken("token", "secret"),
    )


@pytest.fixture
def patch_check_title_blacklisted(mocker):
    """Patch check_title_blacklisted to return not blacklisted"""
    mock_client = mocker.MagicMock()
    mock_client.check_title_blacklisted.return_value = (False, "")
    return mocker.patch(
        "curator.workers.ingest.create_mediawiki_client", return_value=mock_client
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

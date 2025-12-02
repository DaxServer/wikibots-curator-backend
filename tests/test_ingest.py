from unittest.mock import Mock, patch
import pytest
from cryptography.fernet import Fernet
import os

from curator.ingest import (
    get_batches,
    ingest_upload,
    get_uploads_by_batch,
)
from curator.app.models import UploadItem
from curator.app.crypto import decrypt_access_token


@pytest.fixture
def mock_session_fixture():
    mock_session = Mock()
    yield mock_session
    mock_session.reset_mock()


@pytest.fixture
def mock_upload_item():
    return UploadItem(
        id="img1",
        input="test_input",
        title="Test Title",
        wikitext="test_wikitext",
        sdc=[{}],
        labels={"key": "label1"},
    )


@pytest.fixture
def mock_payload(mock_upload_item):
    return Mock(handler="mapillary", items=[mock_upload_item])


@pytest.mark.asyncio
async def test_ingest_upload_success(
    mock_payload,
    mock_upload_item,
):
    os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

    mock_session = Mock()
    mock_background_tasks = Mock()
    # BackgroundTasks adds tasks to a list, we can simulate or just inspect calls.
    # But since the implementation uses background_tasks.add_task, we can mock add_task.

    # Use a real list to capture tasks if we want, or just mock add_task
    mock_background_tasks.add_task.side_effect = lambda func, *args, **kwargs: func(
        *args, **kwargs
    )

    mock_req = Mock()
    mock_req.id = 42
    mock_req.status = "pending"
    mock_req.key = "test_key"
    mock_req.batchid = 1

    user = {
        "username": "testuser",
        "userid": "user123",
        "access_token": ("token123", "secret123"),
    }

    with (
        patch(
            "curator.ingest.create_upload_request", return_value=[mock_req]
        ) as mock_create_upload_request,
        patch("curator.ingest.ingest_process_one") as mock_ingest_process_one,
    ):
        # The ingest_upload function calls encrypt_access_token internally.
        # We want to verify that the token passed to the worker is encrypted and decryptable.
        # But since we are patching ingest_process_one, we can inspect its args.

        result = await ingest_upload(
            mock_payload,
            mock_background_tasks,
            user,
            session=mock_session,
        )

        mock_create_upload_request.assert_called_once_with(
            session=mock_session,
            username="testuser",
            userid="user123",
            payload=[mock_upload_item],
            handler="mapillary",
        )
        mock_session.commit.assert_called_once()

        # Check that the task was added to background tasks
        assert mock_background_tasks.add_task.called

        # Check arguments passed to ingest_process_one.delay
        # args: (id, input, encrypted_token, username)
        args = mock_ingest_process_one.delay.call_args[0]
        assert args[0] == 42
        assert args[1] == "test_input"
        assert args[3] == "testuser"

        # Verify token encryption
        encrypted_token = args[2]
        decrypted = decrypt_access_token(encrypted_token)
        assert tuple(decrypted) == ("token123", "secret123")

        assert result == [
            {
                "id": 42,
                "status": "pending",
                "image_id": "test_key",
                "input": "test_input",
                "batch_id": 1,
            }
        ]


@pytest.mark.asyncio
async def test_get_batches_success(mock_session_fixture):
    batch1 = Mock()
    batch1.id = 1
    batch1.uploads = []
    batch1.user = Mock(username="testuser")

    batch2 = Mock()
    batch2.id = 2
    batch2.uploads = []
    batch2.user = Mock(username="testuser")

    mock_batches = [batch1, batch2]

    with (
        patch(
            "curator.ingest.dal_get_batches", return_value=mock_batches
        ) as mock_get_batches,
        patch(
            "curator.ingest.count_batches", return_value=len(mock_batches)
        ) as mock_count_batches,
    ):
        result = await get_batches(
            userid="user123",
            page=1,
            limit=100,
            session=mock_session_fixture,
        )

        mock_get_batches.assert_called_once_with(
            mock_session_fixture, userid="user123", offset=0, limit=100
        )
        mock_count_batches.assert_called_once_with(
            mock_session_fixture, userid="user123"
        )
        assert result["total"] == 2
        assert len(result["items"]) == 2
        assert result["items"][0]["username"] == "testuser"


@pytest.mark.asyncio
async def test_get_batches_all(mock_session_fixture):
    batch1 = Mock()
    batch1.id = 1
    batch1.uploads = []
    batch1.user = Mock(username="testuser")

    batch2 = Mock()
    batch2.id = 2
    batch2.uploads = []
    batch2.user = Mock(username="otheruser")

    mock_batches = [batch1, batch2]

    with (
        patch(
            "curator.ingest.dal_get_batches", return_value=mock_batches
        ) as mock_get_batches,
        patch("curator.ingest.count_batches", return_value=2) as mock_count_batches,
    ):
        result = await get_batches(
            userid=None, page=1, limit=100, session=mock_session_fixture
        )

        mock_get_batches.assert_called_once_with(
            mock_session_fixture, userid=None, offset=0, limit=100
        )
        mock_count_batches.assert_called_once_with(mock_session_fixture, userid=None)
        assert result["total"] == 2
        assert len(result["items"]) == 2
        assert result["items"][0]["username"] == "testuser"
        assert result["items"][1]["username"] == "otheruser"


@pytest.mark.asyncio
async def test_get_batches_pagination(mock_session_fixture):
    batch = Mock()
    batch.id = 1
    batch.uploads = []
    batch.user = Mock(username="testuser")

    mock_batches = [batch]

    with (
        patch(
            "curator.ingest.dal_get_batches", return_value=mock_batches
        ) as mock_get_batches,
        patch("curator.ingest.count_batches", return_value=1) as mock_count_batches,
    ):
        result_page1 = await get_batches(
            userid="user123",
            page=1,
            limit=1,
            session=mock_session_fixture,
        )

        mock_get_batches.assert_called_once_with(
            mock_session_fixture, userid="user123", offset=0, limit=1
        )
        mock_count_batches.assert_called_once_with(
            mock_session_fixture, userid="user123"
        )
        assert len(result_page1["items"]) == 1

    with (
        patch(
            "curator.ingest.dal_get_batches", return_value=[]
        ) as mock_get_batches_page2,
    ):
        result_page2 = await get_batches(
            userid="user123",
            page=2,
            limit=1,
            session=mock_session_fixture,
        )

        mock_get_batches_page2.assert_called_once_with(
            mock_session_fixture, userid="user123", offset=1, limit=1
        )
        assert len(result_page2["items"]) == 0


@pytest.mark.asyncio
async def test_get_uploads_by_batch_success():
    upload1 = Mock()
    upload1.id = "req-1"
    upload1.status = "completed"
    upload1.key = "image1"
    upload1.batch_id = 1
    upload1.result = {"some": "result"}
    upload1.error = None
    upload1.success = True
    upload1.handler = "mapillary"
    upload1.batchid = 1

    upload2 = Mock()
    upload2.id = "req-2"
    upload2.status = "failed"
    upload2.key = "image2"
    upload2.batch_id = 1
    upload2.result = None
    upload2.error = '{"msg": "something went wrong"}'
    upload2.success = False
    upload2.handler = "other_handler"

    mock_items = [upload1, upload2]
    mock_session = Mock()

    with (
        patch(
            "curator.ingest.get_upload_request", return_value=mock_items
        ) as mock_get_uploads,
        patch("curator.ingest.count_uploads_in_batch", return_value=2) as mock_count,
    ):
        result = await get_uploads_by_batch(
            batch_id=1,
            page=1,
            limit=100,
            session=mock_session,
        )

        mock_get_uploads.assert_called_once_with(
            mock_session,
            batch_id=1,
            offset=0,
            limit=100,
            columns=[
                "id",
                "status",
                "key",
                "batchid",
                "error",
                "success",
                "handler",
            ],
        )
        mock_count.assert_called_once_with(mock_session, batch_id=1)

        assert "items" in result
        assert "total" in result
        assert result["total"] == 2
        assert len(result["items"]) == 2
        first = result["items"][0]
        assert first["id"] == "req-1"
        assert first["status"] == "completed"
        assert first["key"] == "image1"
        assert first["batchid"] == 1
        assert first["error"] is None
        assert first["success"] is True
        assert first["handler"] == "mapillary"

        second = result["items"][1]
        assert second["error"] == '{"msg": "something went wrong"}'


@pytest.mark.asyncio
async def test_get_uploads_by_batch_pagination():
    upload = Mock()
    upload.id = "req-1"
    upload.status = "completed"
    upload.key = "image1"
    upload.batch_id = 1
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
        result = await get_uploads_by_batch(
            batch_id=1,
            page=3,
            limit=25,
            session=mock_session,
        )

        mock_get_uploads.assert_called_once_with(
            mock_session,
            batch_id=1,
            offset=50,
            limit=25,
            columns=[
                "id",
                "status",
                "key",
                "batchid",
                "error",
                "success",
                "handler",
            ],
        )
        mock_count.assert_called_once_with(mock_session, batch_id=1)
        assert result["total"] == 1
        assert len(result["items"]) == 1

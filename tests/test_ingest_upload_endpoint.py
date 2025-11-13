from unittest.mock import Mock, patch
from fastapi import BackgroundTasks
import os
from cryptography.fernet import Fernet
from curator.mapillary import ingest_upload
from curator.app.models import UploadItem, UploadRequest
from curator.app.crypto import decrypt_access_token


def test_ingest_upload_enqueues_with_integer_ids():
    os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    # Prepare request session with required fields
    mock_request = Mock()
    mock_request.session = {
        "user": {"username": "test_user", "sub": "user123"},
        "access_token": ("token123", "secret123"),
    }

    # Prepare payload
    payload = [UploadItem(id="img1", sequence_id="seq1", title="T1", wikitext="W1")]

    # Mock session and create_upload_request to return UploadRequest with id
    mock_session = Mock()

    upload_req = Mock(spec=UploadRequest)
    upload_req.id = 42
    upload_req.userid = "user123"
    upload_req.batch_id = "batch-x"
    upload_req.key = "img1"
    upload_req.filename = "T1"
    upload_req.wikitext = "W1"
    upload_req.status = "queued"

    with patch("curator.mapillary.create_upload_request", return_value=[upload_req]):
        with patch("curator.mapillary.process_one.delay") as mock_delay:
            # BackgroundTasks can be real; it just collects tasks
            bg = BackgroundTasks()

            # Call endpoint function
            result = ingest_upload(mock_request, payload, bg, mock_session)

            # Ensure commit was called to materialize IDs
            mock_session.commit.assert_called_once()

            # BackgroundTasks should have scheduled the Celery task with integer id
            # Inspect the queued tasks to ensure correct function and args
            assert len(bg.tasks) == 1
            task = bg.tasks[0]
            assert task.func is mock_delay
            assert task.args[0] == 42
            assert task.args[1] == "seq1"
            assert isinstance(task.args[2], str)
            assert tuple(decrypt_access_token(task.args[2])) == (
                "token123",
                "secret123",
            )
            assert task.args[3] == "test_user"

            assert result == [
                {
                    "id": 42,
                    "status": "queued",
                    "image_id": "img1",
                    "sequence_id": "seq1",
                    "batch_id": "batch-x",
                }
            ]

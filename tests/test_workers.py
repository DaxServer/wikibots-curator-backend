import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet

import curator.workers.ingest as worker
from curator.app.crypto import encrypt_access_token
from curator.app.models import UploadRequest


@pytest.mark.asyncio
async def test_worker_process_one_decrypts_token():
    os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

    item = SimpleNamespace(
        id=1,
        batchid=1,
        userid="u",
        status="queued",
        key="img1",
        handler="mapillary",
        filename="File.jpg",
        wikitext="",
        labels={"en": {"language": "en", "value": "Example"}},
        sdc=None,
        collection="seq",
        access_token=encrypt_access_token(("t", "s")),
        user=SimpleNamespace(username="User"),
    )

    def fake_session_iter():
        yield SimpleNamespace(close=lambda: None)

    captured = {}

    with (
        patch("curator.workers.ingest.get_session", fake_session_iter),
        patch("curator.workers.ingest.get_upload_request_by_id", return_value=item),
        patch("curator.workers.ingest.update_upload_status"),
        patch(
            "curator.workers.ingest.upload_file_chunked",
            side_effect=lambda **kwargs: (
                captured.setdefault("token", kwargs["access_token"]),
                {
                    "result": "success",
                    "title": kwargs["file_name"],
                    "url": kwargs["file_url"],
                },
            )[1],
        ),
        patch("curator.workers.ingest.clear_upload_access_token"),
        patch(
            "curator.workers.ingest.MapillaryHandler.fetch_image_metadata",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                id="img1",
                url_original="https://example.com/file.jpg",
            ),
        ),
    ):
        ok = await worker.process_one(1)
        assert ok is True
        assert tuple(captured["token"]) == ("t", "s")


@pytest.mark.asyncio
async def test_worker_process_one_duplicate_status():
    os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

    item = SimpleNamespace(
        id=1,
        batchid=1,
        userid="u",
        status="queued",
        key="img1",
        handler="mapillary",
        filename="File.jpg",
        wikitext="",
        labels={"en": {"language": "en", "value": "Example"}},
        sdc=None,
        collection="seq",
        access_token=encrypt_access_token(("t", "s")),
        user=SimpleNamespace(username="User"),
    )

    def fake_session_iter():
        yield SimpleNamespace(close=lambda: None)

    captured_status = {}

    def capture_status(session, upload_id, status, error=None, success=None):
        captured_status["status"] = status
        captured_status["error"] = error

    with (
        patch("curator.workers.ingest.get_session", fake_session_iter),
        patch("curator.workers.ingest.get_upload_request_by_id", return_value=item),
        patch(
            "curator.workers.ingest.update_upload_status", side_effect=capture_status
        ),
        patch(
            "curator.workers.ingest.upload_file_chunked",
            side_effect=worker.DuplicateUploadError(
                duplicates=[{"title": "File:Existing.jpg", "url": "http://commons..."}],
                message="Duplicate file",
            ),
        ),
        patch("curator.workers.ingest.clear_upload_access_token"),
        patch(
            "curator.workers.ingest.MapillaryHandler.fetch_image_metadata",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                id="img1",
                url_original="https://example.com/file.jpg",
            ),
        ),
    ):
        ok = await worker.process_one(1)
        assert ok is False
        assert captured_status["status"] == "duplicate"
        assert captured_status["error"]["type"] == "duplicate"


def test_upload_request_access_token_excluded_from_model_dump():
    upload = UploadRequest(
        id=1,
        batchid=1,
        userid="u",
        status="queued",
        key="img1",
        handler="mapillary",
        collection="seq",
        access_token="secret",
        filename="File.jpg",
        wikitext="wikitext",
    )

    dumped = upload.model_dump(mode="json")

    assert "access_token" not in dumped

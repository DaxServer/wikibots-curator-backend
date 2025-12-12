import os
from cryptography.fernet import Fernet
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

import pytest

from curator.app.crypto import encrypt_access_token
import curator.workers.ingest as worker


@pytest.mark.asyncio
async def test_worker_process_one_decrypts_token():
    os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

    encrypted = encrypt_access_token(("t", "s"))

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
        encrypted_access_token=encrypted,
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

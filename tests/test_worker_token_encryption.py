import os
from cryptography.fernet import Fernet
from types import SimpleNamespace
from unittest.mock import patch
from curator.app.crypto import encrypt_access_token
import curator.workers.ingest as worker


def test_worker_process_one_decrypts_token():
    os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

    encrypted = encrypt_access_token(("t", "s"))

    item = SimpleNamespace(
        id=1,
        batch_id="b",
        userid="u",
        status="queued",
        key="img1",
        handler="mapillary",
        filename="File.jpg",
        wikitext="",
        labels={"en": {"language": "en", "value": "Example"}},
        sdc=None,
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
            side_effect=lambda file_name, file_url, access_token, **kwargs: (
                captured.setdefault("token", access_token),
                {"result": "success", "title": file_name, "url": file_url},
            )[1],
        ),
        patch("curator.workers.ingest.count_open_uploads_for_batch", return_value=0),
        patch(
            "curator.workers.ingest.MapillaryHandler.fetch_image_metadata",
            return_value=SimpleNamespace(
                id="img1",
                url_original="https://example.com/file.jpg",
            ),
        ),
        patch(
            "curator.workers.ingest.MapillaryHandler.build_sdc",
            return_value=[],
        ),
    ):

        ok = worker.process_one(1, "seq", encrypted, "User")
        assert ok is True
        assert tuple(captured["token"]) == ("t", "s")

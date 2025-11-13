import os
from types import SimpleNamespace
from cryptography.fernet import Fernet
from curator.app.crypto import encrypt_access_token
import curator.workers.mapillary as worker


def test_worker_process_one_decrypts_token(monkeypatch):
    os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    access_token = ("t", "s")
    encrypted = encrypt_access_token(access_token)

    class FakeSession:
        def close(self):
            pass

    def fake_get_session():
        yield FakeSession()

    item = worker.UploadRequest(
        id=1,
        batch_id="b",
        userid="u",
        status="queued",
        key="img1",
        handler="mapillary",
        filename="File.jpg",
        wikitext="",
    )

    def fake_get_upload_request_by_id(session, upload_id):
        return item

    def fake_update_upload_status(session, upload_id, status, result=None, error=None):
        return None

    def fake_fetch_sequence_data(sequence_id):
        return {
            "img1": {
                "id": "img1",
                "thumb_original_url": "https://example.com/file.jpg",
            }
        }

    def fake_build_mapillary_sdc(image):
        return []

    captured = {}

    def fake_upload_file_chunked(
        file_name, file_url, wikitext, access_token, username, edit_summary, sdc
    ):
        captured["token"] = access_token
        return {"result": "success", "title": file_name, "url": file_url}

    monkeypatch.setattr(worker, "get_session", fake_get_session)
    monkeypatch.setattr(
        worker, "get_upload_request_by_id", fake_get_upload_request_by_id
    )
    monkeypatch.setattr(worker, "update_upload_status", fake_update_upload_status)
    monkeypatch.setattr(worker, "fetch_sequence_data", fake_fetch_sequence_data)
    monkeypatch.setattr(worker, "build_mapillary_sdc", fake_build_mapillary_sdc)
    monkeypatch.setattr(worker, "upload_file_chunked", fake_upload_file_chunked)
    monkeypatch.setattr(
        worker, "count_open_uploads_for_batch", lambda *args, **kwargs: 0
    )

    ok = worker.process_one(1, "seq", encrypted, "User")
    assert ok is True
    assert tuple(captured["token"]) == ("t", "s")

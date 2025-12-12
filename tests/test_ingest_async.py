import json
from types import SimpleNamespace

from typing import Any

import pytest


class DummySession:
    def close(self):
        pass


class DummyImage:
    def __init__(self, id: str, url: str):
        self.id = id
        self.url_original = url


class Calls:
    def __init__(self):
        self.status_updates: list[tuple[int, str, dict | None]] = []


@pytest.mark.asyncio
async def test_process_one_runs_async(monkeypatch):
    from curator.workers import ingest as mod

    calls = Calls()

    def fake_get_session():
        yield DummySession()

    class DummyItem:
        def __init__(self):
            self.id = 1
            self.batchid = 123
            self.userid = "u1"
            self.key = "img-1"
            self.filename = "Test.jpg"
            self.wikitext = "== Summary =="
            self.sdc = json.dumps([{"P180": "Q42"}])
            self.labels = {"en": "Test"}
            self.collection = "seq-1"
            self.access_token = "cipher"
            self.user = SimpleNamespace(username="user1")

    def fake_get_upload_request_by_id(session: Any, upload_id: int):
        return DummyItem()

    def fake_update_upload_status(session: Any, upload_id: int, status: str, **kw):
        calls.status_updates.append((upload_id, status, kw or None))

    class StubHandler:
        async def fetch_image_metadata(self, image_id: str, input: str):
            return DummyImage(id=image_id, url="https://example.com/file.jpg")

    def fake_decrypt_access_token(ciphertext: str):
        return ("token", "secret")

    def fake_upload_file_chunked(**kwargs):
        return {"url": "https://commons.wikimedia.org/wiki/File:Test.jpg"}

    monkeypatch.setattr(mod, "get_session", fake_get_session)
    monkeypatch.setattr(mod, "get_upload_request_by_id", fake_get_upload_request_by_id)
    monkeypatch.setattr(mod, "update_upload_status", fake_update_upload_status)
    monkeypatch.setattr(mod, "MapillaryHandler", StubHandler)
    monkeypatch.setattr(mod, "decrypt_access_token", fake_decrypt_access_token)
    monkeypatch.setattr(mod, "upload_file_chunked", fake_upload_file_chunked)
    monkeypatch.setattr(mod, "clear_upload_access_token", lambda *a, **k: None)

    ok = await mod.process_one(1)

    assert ok is True
    assert calls.status_updates[0][1] == "in_progress"
    assert calls.status_updates[-1][1] == "completed"

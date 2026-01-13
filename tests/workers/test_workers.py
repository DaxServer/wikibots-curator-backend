from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from curator.app.commons import DuplicateUploadError
from curator.app.crypto import encrypt_access_token
from curator.app.models import UploadRequest
from curator.asyncapi import ErrorLink
from curator.workers.ingest import process_one


@pytest.fixture(autouse=True)
def patch_ingest_get_session(patch_get_session):
    return patch_get_session("curator.workers.ingest.get_session")


@pytest.mark.asyncio
async def test_worker_process_one_decrypts_token(mock_session):
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
        copyright_override=False,
        sdc=None,
        collection="seq",
        access_token=encrypt_access_token(("t", "s")),
        user=SimpleNamespace(username="User"),
        last_edited_by=None,
        last_editor=None,
    )

    captured = {}

    with (
        patch("curator.workers.ingest.get_upload_request_by_id", return_value=item),
        patch("curator.workers.ingest.update_upload_status"),
        patch(
            "curator.workers.ingest.check_title_blacklisted", return_value=(False, "")
        ),
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
                creator=SimpleNamespace(username="alice"),
                dates=SimpleNamespace(taken="2023-01-01T00:00:00Z"),
                urls=SimpleNamespace(
                    url="https://example.com/photo",
                    original="https://example.com/file.jpg",
                    preview="https://example.com/preview",
                    thumbnail="https://example.com/thumb",
                ),
                location=SimpleNamespace(
                    latitude=1.0, longitude=2.0, compass_angle=3.0
                ),
                dimensions=SimpleNamespace(width=100, height=200),
                camera=SimpleNamespace(make=None, model=None, is_pano=None),
            ),
        ),
    ):
        ok = await process_one(1, "test_edit_group_abc123")
        assert ok is True
        assert tuple(captured["token"]) == ("t", "s")


@pytest.mark.asyncio
async def test_worker_process_one_duplicate_status(mock_session):
    """Test that process_one marks duplicate status when file already exists."""
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
        copyright_override=False,
        sdc=None,
        collection="seq",
        access_token=encrypt_access_token(("t", "s")),
        user=SimpleNamespace(username="User"),
        last_edited_by=None,
        last_editor=None,
    )

    captured_status = {}

    def capture_status(session, upload_id, status, error=None, success=None):
        captured_status["status"] = status
        captured_status["error"] = error

    with (
        patch("curator.workers.ingest.get_upload_request_by_id", return_value=item),
        patch(
            "curator.workers.ingest.update_upload_status", side_effect=capture_status
        ),
        patch(
            "curator.workers.ingest.check_title_blacklisted", return_value=(False, "")
        ),
        patch(
            "curator.workers.ingest.upload_file_chunked",
            side_effect=DuplicateUploadError(
                duplicates=[
                    ErrorLink(title="File:Existing.jpg", url="http://commons...")
                ],
                message="Duplicate file",
            ),
        ),
        patch("curator.workers.ingest.clear_upload_access_token"),
        patch(
            "curator.workers.ingest.MapillaryHandler.fetch_image_metadata",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                id="img1",
                creator=SimpleNamespace(username="alice"),
                dates=SimpleNamespace(taken="2023-01-01T00:00:00Z"),
                urls=SimpleNamespace(
                    url="https://example.com/photo",
                    original="https://example.com/file.jpg",
                    preview="https://example.com/preview",
                    thumbnail="https://example.com/thumb",
                ),
                location=SimpleNamespace(
                    latitude=1.0, longitude=2.0, compass_angle=3.0
                ),
                dimensions=SimpleNamespace(width=100, height=200),
                camera=SimpleNamespace(make=None, model=None, is_pano=None),
            ),
        ),
        # Mock the entire SDC merge handler to return None (merge failed)
        # This will cause it to fall back to marking as duplicate
        patch(
            "curator.workers.ingest._handle_duplicate_with_sdc_merge",
            new_callable=AsyncMock,
            return_value=(None, None),  # (url, status) - None means merge failed
        ),
    ):
        ok = await process_one(1, "test_edit_group_abc123")
        assert ok is False
        assert captured_status["status"] == "duplicate"
        assert captured_status["error"].type == "duplicate"


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


@pytest.mark.asyncio
async def test_worker_process_one_fails_on_blacklisted_title(mock_session):
    """Test that process_one fails when title is blacklisted."""
    item = SimpleNamespace(
        id=1,
        batchid=1,
        userid="u",
        status="queued",
        key="img1",
        handler="mapillary",
        filename="BlacklistedFile.jpg",
        wikitext="",
        labels={"en": {"language": "en", "value": "Example"}},
        copyright_override=False,
        sdc=None,
        collection="seq",
        access_token=encrypt_access_token(("t", "s")),
        user=SimpleNamespace(username="User"),
        last_edited_by=None,
        last_editor=None,
    )

    captured_status = {}

    def capture_status(session, upload_id, status, error=None, success=None):
        captured_status["status"] = status
        captured_status["error"] = error

    with (
        patch("curator.workers.ingest.get_upload_request_by_id", return_value=item),
        patch(
            "curator.workers.ingest.update_upload_status", side_effect=capture_status
        ),
        patch(
            "curator.workers.ingest.check_title_blacklisted",
            return_value=(True, "Title contains blacklisted pattern"),
        ),
        patch("curator.workers.ingest.clear_upload_access_token"),
        patch(
            "curator.workers.ingest.MapillaryHandler.fetch_image_metadata",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                id="img1",
                creator=SimpleNamespace(username="alice"),
                dates=SimpleNamespace(taken="2023-01-01T00:00:00Z"),
                urls=SimpleNamespace(
                    url="https://example.com/photo",
                    original="https://example.com/file.jpg",
                    preview="https://example.com/preview",
                    thumbnail="https://example.com/thumb",
                ),
                location=SimpleNamespace(
                    latitude=1.0, longitude=2.0, compass_angle=3.0
                ),
                dimensions=SimpleNamespace(width=100, height=200),
                camera=SimpleNamespace(make=None, model=None, is_pano=None),
            ),
        ),
    ):
        ok = await process_one(1, "test_edit_group_abc123")
        assert ok is False
        assert captured_status["status"] == "failed"
        assert captured_status["error"].type == "title_blacklisted"
        assert captured_status["error"].message == "Title contains blacklisted pattern"


@pytest.mark.asyncio
async def test_worker_process_one_uploadstash_retry_success(mock_session):
    """Test that process_one retries uploadstash-file-not-found errors and succeeds on retry."""
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
        copyright_override=False,
        sdc=None,
        collection="seq",
        access_token=encrypt_access_token(("t", "s")),
        user=SimpleNamespace(username="User"),
        last_edited_by=None,
        last_editor=None,
    )

    upload_attempts = []

    def mock_upload_file_chunked(**kwargs):
        upload_attempts.append(len(upload_attempts) + 1)
        # Fail on first attempt with uploadstash-file-not-found error, succeed on second
        if len(upload_attempts) == 1:
            raise Exception(
                'uploadstash-file-not-found: Key "1cbv2eph0ceg.op0el3.7498417.jpg" not found in stash. [servedby: mw-api-ext.codfw.main-6c9d649c6d-dfvpl; help: See https://commons.wikimedia.org/w/api.php for API usage.]'
            )
        return {
            "result": "success",
            "title": kwargs["file_name"],
            "url": kwargs["file_url"],
        }

    with (
        patch("curator.workers.ingest.get_upload_request_by_id", return_value=item),
        patch("curator.workers.ingest.update_upload_status"),
        patch(
            "curator.workers.ingest.check_title_blacklisted", return_value=(False, "")
        ),
        patch(
            "curator.workers.ingest.upload_file_chunked",
            side_effect=mock_upload_file_chunked,
        ),
        patch("curator.workers.ingest.clear_upload_access_token"),
        patch(
            "curator.workers.ingest.MapillaryHandler.fetch_image_metadata",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                id="img1",
                creator=SimpleNamespace(username="alice"),
                dates=SimpleNamespace(taken="2023-01-01T00:00:00Z"),
                urls=SimpleNamespace(
                    url="https://example.com/photo",
                    original="https://example.com/file.jpg",
                    preview="https://example.com/preview",
                    thumbnail="https://example.com/thumb",
                ),
                location=SimpleNamespace(
                    latitude=1.0, longitude=2.0, compass_angle=3.0
                ),
                dimensions=SimpleNamespace(width=100, height=200),
                camera=SimpleNamespace(make=None, model=None, is_pano=None),
            ),
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        ok = await process_one(1, "test_edit_group_abc123")
        assert ok is True
        assert (
            len(upload_attempts) == 2
        )  # Should have tried 2 times (MAX_UPLOADSTASH_TRIES)


@pytest.mark.asyncio
async def test_worker_process_one_uploadstash_retry_max_attempts(mock_session):
    """Test that process_one tries uploadstash-file-not-found errors up to MAX_UPLOADSTASH_TRIES attempts."""
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
        copyright_override=False,
        sdc=None,
        collection="seq",
        access_token=encrypt_access_token(("t", "s")),
        user=SimpleNamespace(username="User"),
        last_edited_by=None,
        last_editor=None,
    )

    def fake_session_iter():
        yield mock_session

    upload_attempts = []
    captured_status = {}

    def capture_status(session, upload_id, status, error=None, success=None):
        captured_status["status"] = status
        captured_status["error"] = error

    def mock_upload_file_chunked(**kwargs):
        upload_attempts.append(len(upload_attempts) + 1)
        # Always fail with uploadstash-file-not-found error
        raise Exception(
            'uploadstash-file-not-found: Key "1cbv2eph0ceg.op0el3.7498417.jpg" not found in stash. [servedby: mw-api-ext.codfw.main-6c9d649c6d-dfvpl; help: See https://commons.wikimedia.org/w/api.php for API usage.]'
        )

    with (
        patch("curator.workers.ingest.get_upload_request_by_id", return_value=item),
        patch(
            "curator.workers.ingest.update_upload_status", side_effect=capture_status
        ),
        patch(
            "curator.workers.ingest.check_title_blacklisted", return_value=(False, "")
        ),
        patch(
            "curator.workers.ingest.upload_file_chunked",
            side_effect=mock_upload_file_chunked,
        ),
        patch("curator.workers.ingest.clear_upload_access_token"),
        patch(
            "curator.workers.ingest.MapillaryHandler.fetch_image_metadata",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                id="img1",
                creator=SimpleNamespace(username="alice"),
                dates=SimpleNamespace(taken="2023-01-01T00:00:00Z"),
                urls=SimpleNamespace(
                    url="https://example.com/photo",
                    original="https://example.com/file.jpg",
                    preview="https://example.com/preview",
                    thumbnail="https://example.com/thumb",
                ),
                location=SimpleNamespace(
                    latitude=1.0, longitude=2.0, compass_angle=3.0
                ),
                dimensions=SimpleNamespace(width=100, height=200),
                camera=SimpleNamespace(make=None, model=None, is_pano=None),
            ),
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        ok = await process_one(1, "test_edit_group_abc123")
        assert ok is False
        assert len(upload_attempts) == 2  # Should have tried 2 times
        assert captured_status["status"] == "failed"
        assert captured_status["error"].type == "error"
        # The error message should contain the original uploadstash-file-not-found error
        assert "uploadstash-file-not-found" in captured_status["error"].message


@pytest.mark.asyncio
async def test_worker_process_one_uploadstash_retry_different_error(mock_session):
    """Test that process_one doesn't retry non-uploadstash errors."""
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
        copyright_override=False,
        sdc=None,
        collection="seq",
        access_token=encrypt_access_token(("t", "s")),
        user=SimpleNamespace(username="User"),
        last_edited_by=None,
        last_editor=None,
    )

    def fake_session_iter():
        yield mock_session

    upload_attempts = []
    captured_status = {}

    def capture_status(session, upload_id, status, error=None, success=None):
        captured_status["status"] = status
        captured_status["error"] = error

    def mock_upload_file_chunked(**kwargs):
        upload_attempts.append(len(upload_attempts) + 1)
        # Fail with a different error (not uploadstash-file-not-found)
        raise Exception("Network timeout or some other error")

    with (
        patch("curator.workers.ingest.get_upload_request_by_id", return_value=item),
        patch(
            "curator.workers.ingest.update_upload_status", side_effect=capture_status
        ),
        patch(
            "curator.workers.ingest.check_title_blacklisted", return_value=(False, "")
        ),
        patch(
            "curator.workers.ingest.upload_file_chunked",
            side_effect=mock_upload_file_chunked,
        ),
        patch("curator.workers.ingest.clear_upload_access_token"),
        patch(
            "curator.workers.ingest.MapillaryHandler.fetch_image_metadata",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                id="img1",
                creator=SimpleNamespace(username="alice"),
                dates=SimpleNamespace(taken="2023-01-01T00:00:00Z"),
                urls=SimpleNamespace(
                    url="https://example.com/photo",
                    original="https://example.com/file.jpg",
                    preview="https://example.com/preview",
                    thumbnail="https://example.com/thumb",
                ),
                location=SimpleNamespace(
                    latitude=1.0, longitude=2.0, compass_angle=3.0
                ),
                dimensions=SimpleNamespace(width=100, height=200),
                camera=SimpleNamespace(make=None, model=None, is_pano=None),
            ),
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),  # Mock sleep to avoid delays
    ):
        ok = await process_one(1, "test_edit_group_abc123")
        assert ok is False
        assert len(upload_attempts) == 1  # Should have tried only once (no retry)
        assert captured_status["status"] == "failed"
        assert captured_status["error"].type == "error"
        assert "Network timeout or some other error" in captured_status["error"].message


@pytest.mark.asyncio
async def test_worker_process_one_includes_edit_group_id_in_summary(mock_session):
    """Test that process_one includes edit_group_id in the edit summary."""
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
        copyright_override=False,
        sdc=None,
        collection="seq",
        access_token=encrypt_access_token(("t", "s")),
        user=SimpleNamespace(username="User"),
        last_edited_by=None,
        last_editor=None,
    )

    captured_edit_summary = {}

    def mock_upload_file_chunked(**kwargs):
        captured_edit_summary["summary"] = kwargs.get("edit_summary", "")
        return {
            "result": "success",
            "title": kwargs["file_name"],
            "url": kwargs["file_url"],
        }

    with (
        patch("curator.workers.ingest.get_upload_request_by_id", return_value=item),
        patch("curator.workers.ingest.update_upload_status"),
        patch(
            "curator.workers.ingest.check_title_blacklisted", return_value=(False, "")
        ),
        patch(
            "curator.workers.ingest.upload_file_chunked",
            side_effect=mock_upload_file_chunked,
        ),
        patch("curator.workers.ingest.clear_upload_access_token"),
        patch(
            "curator.workers.ingest.MapillaryHandler.fetch_image_metadata",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                id="img1",
                creator=SimpleNamespace(username="alice"),
                dates=SimpleNamespace(taken="2023-01-01T00:00:00Z"),
                urls=SimpleNamespace(
                    url="https://example.com/photo",
                    original="https://example.com/file.jpg",
                    preview="https://example.com/preview",
                    thumbnail="https://example.com/thumb",
                ),
                location=SimpleNamespace(
                    latitude=1.0, longitude=2.0, compass_angle=3.0
                ),
                dimensions=SimpleNamespace(width=100, height=200),
                camera=SimpleNamespace(make=None, model=None, is_pano=None),
            ),
        ),
    ):
        test_edit_group_id = "abc123def456"
        ok = await process_one(1, test_edit_group_id)
        assert ok is True
        # Verify the edit summary includes the edit group link
        assert test_edit_group_id in captured_edit_summary["summary"]
        assert (
            "[[:toolforge:editgroups-commons/b/curator/"
            in captured_edit_summary["summary"]
        )
        assert "|details]]" in captured_edit_summary["summary"]

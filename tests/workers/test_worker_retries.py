"""Tests for worker upload retry logic."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from curator.app.crypto import encrypt_access_token
from curator.workers.ingest import process_one


@pytest.fixture(autouse=True)
def patch_ingest_get_session(patch_get_session):
    return patch_get_session("curator.workers.ingest.get_session")


@pytest.mark.asyncio
async def test_worker_process_one_uploadstash_retry_success(
    mocker, mock_session, mock_isolated_site
):
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

    def mock_upload_file_chunked(
        file_name,
        file_url,
        wikitext,
        edit_summary,
        upload_id,
        batch_id,
        mediawiki_client,
        sdc=None,
        labels=None,
    ):
        upload_attempts.append(len(upload_attempts) + 1)
        # Fail on first attempt with uploadstash-file-not-found error, succeed on second
        if len(upload_attempts) == 1:
            raise Exception(
                'uploadstash-file-not-found: Key "1cbv2eph0ceg.op0el3.7498417.jpg" not found in stash. [servedby: mw-api-ext.codfw.main-6c9d649c6d-dfvpl; help: See https://commons.wikimedia.org/w/api.php for API usage.]'
            )
        return {
            "result": "success",
            "title": file_name,
            "url": file_url,
        }

    with (
        patch("curator.workers.ingest.get_upload_request_by_id", return_value=item),
        patch("curator.workers.ingest.update_upload_status"),
        patch("curator.workers.ingest.create_mediawiki_client") as mock_client_patch,
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
        mock_client = mocker.MagicMock()
        mock_client.check_title_blacklisted.return_value = (False, "")
        mock_client_patch.return_value = mock_client

        ok = await process_one(1, "test_edit_group_abc123")
        assert ok is True
        assert (
            len(upload_attempts) == 2
        )  # Should have tried 2 times (MAX_UPLOADSTASH_TRIES)


@pytest.mark.asyncio
async def test_worker_process_one_uploadstash_retry_max_attempts(
    mocker, mock_session, mock_isolated_site
):
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

    def mock_upload_file_chunked(*args, **kwargs):
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
        patch("curator.workers.ingest.create_mediawiki_client") as mock_client_patch,
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
        mock_client = mocker.MagicMock()
        mock_client.check_title_blacklisted.return_value = (False, "")
        mock_client_patch.return_value = mock_client

        ok = await process_one(1, "test_edit_group_abc123")
        assert ok is False
        assert len(upload_attempts) == 2  # Should have tried 2 times
        assert captured_status["status"] == "failed"
        assert captured_status["error"].type == "error"
        # The error message should contain the original uploadstash-file-not-found error
        assert "uploadstash-file-not-found" in captured_status["error"].message

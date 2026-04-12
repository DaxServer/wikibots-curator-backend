"""Tests for worker upload retry logic."""

import functools
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from mwoauth import AccessToken

from curator.core.crypto import encrypt_access_token
from curator.workers.ingest import process_one

_UPLOADSTASH_FILE_NOT_FOUND_ERROR = (
    'uploadstash-file-not-found: Key "1cbv2eph0ceg.op0el3.7498417.jpg" not found in stash.'
    " [servedby: mw-api-ext.codfw.main-6c9d649c6d-dfvpl;"
    " help: See https://commons.wikimedia.org/w/api.php for API usage.]"
)


def _capture_status(captured: dict, session, upload_id, status, error=None, success=None):
    captured["status"] = status
    captured["error"] = error


@pytest.fixture(autouse=True)
def patch_ingest_get_session(patch_get_session):
    return patch_get_session("curator.workers.ingest.get_session")


@pytest.fixture
def upload_item():
    return SimpleNamespace(
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
        access_token=encrypt_access_token(AccessToken("t", "s")),
        user=SimpleNamespace(username="User"),
    )


@pytest.fixture
def mock_ingest_patches(mocker, upload_item):
    """Patches all common ingest dependencies. Returns the update_upload_status mock."""
    mocker.patch("curator.workers.ingest.get_upload_request_by_id", return_value=upload_item)
    update_status = mocker.patch("curator.workers.ingest.update_upload_status")
    mocker.patch("curator.workers.ingest.clear_upload_access_token")
    mocker.patch(
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
            location=SimpleNamespace(latitude=1.0, longitude=2.0, compass_angle=3.0),
            dimensions=SimpleNamespace(width=100, height=200),
            camera=SimpleNamespace(make=None, model=None, is_pano=None),
        ),
    )
    mocker.patch("asyncio.sleep", new_callable=AsyncMock)
    mock_client = mocker.MagicMock()
    mock_client.check_title_blacklisted.return_value = (False, "")
    mocker.patch("curator.workers.ingest.MediaWikiClient", return_value=mock_client)
    return update_status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_message",
    [
        _UPLOADSTASH_FILE_NOT_FOUND_ERROR,
        "uploadstash-bad-path: Path doesn't exist.",
        "stashfailed: No chunked upload session with this key.",
    ],
    ids=["uploadstash-file-not-found", "uploadstash-bad-path", "stashfailed-session-not-found"],
)
async def test_worker_process_one_stash_gone_retry_success(
    mock_session, mock_isolated_site, mock_ingest_patches, error_message
):
    """Test that process_one retries stash-gone errors and succeeds on retry."""
    with patch(
        "curator.workers.ingest.upload_file_chunked",
        side_effect=[
            Exception(error_message),
            {"result": "success", "title": "File.jpg", "url": "https://example.com"},
        ],
    ) as mock_chunked:
        ok = await process_one(1, "test_edit_group_abc123")

    assert ok is True
    assert mock_chunked.call_count == 2


@pytest.mark.asyncio
async def test_worker_process_one_uploadstash_retry_max_attempts(
    mock_session, mock_isolated_site, mock_ingest_patches
):
    """Test that process_one gives up after MAX_UPLOADSTASH_TRIES attempts."""
    captured_status: dict = {}
    mock_ingest_patches.side_effect = functools.partial(_capture_status, captured_status)

    with patch(
        "curator.workers.ingest.upload_file_chunked",
        side_effect=Exception(_UPLOADSTASH_FILE_NOT_FOUND_ERROR),
    ) as mock_chunked:
        ok = await process_one(1, "test_edit_group_abc123")

    assert ok is False
    assert mock_chunked.call_count == 2
    assert captured_status["status"] == "failed"
    assert captured_status["error"].type == "error"
    assert "uploadstash-file-not-found" in captured_status["error"].message

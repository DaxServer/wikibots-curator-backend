"""Tests for StorageError handling in worker tasks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mwoauth import AccessToken

from curator.core.crypto import encrypt_access_token
from curator.core.errors import StorageError
from curator.workers.ingest import process_one
from curator.workers.tasks import STORAGE_ERROR_DELAYS, process_upload

_UPLOADSTASH_EXCEPTION_ERROR = (
    "uploadstash-exception: Could not store upload in the stash "
    "(MediaWiki\\Upload\\Exception\\UploadStashFileException): "
    '"Im Speicher-Backend „local-swift-eqiad" ist ein unbekannter Fehler aufgetreten.".'
)


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


@pytest.fixture(autouse=True)
def patch_ingest_get_session(patch_get_session):
    return patch_get_session("curator.workers.ingest.get_session")


@pytest.fixture
def mock_mapillary_image():
    return SimpleNamespace(
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
    )


@pytest.mark.asyncio
async def test_process_one_raises_storage_error_on_uploadstash_exception(
    mocker, mock_session, mock_isolated_site, upload_item, mock_mapillary_image
):
    """process_one propagates StorageError when upload_file_chunked fails with uploadstash-exception."""
    captured_status = {}

    def capture_status(session, upload_id, status, **kwargs):
        captured_status["status"] = status

    with (
        patch(
            "curator.workers.ingest.get_upload_request_by_id", return_value=upload_item
        ),
        patch(
            "curator.workers.ingest.update_upload_status", side_effect=capture_status
        ),
        patch("curator.workers.ingest.MediaWikiClient") as mock_client_patch,
        patch(
            "curator.workers.ingest.upload_file_chunked",
            side_effect=ValueError(_UPLOADSTASH_EXCEPTION_ERROR),
        ),
        patch("curator.workers.ingest.clear_upload_access_token"),
        patch(
            "curator.workers.ingest.MapillaryHandler.fetch_image_metadata",
            new_callable=AsyncMock,
            return_value=mock_mapillary_image,
        ),
    ):
        mock_client = mocker.MagicMock()
        mock_client.check_title_blacklisted.return_value = (False, "")
        mock_client_patch.return_value = mock_client

        with pytest.raises(StorageError):
            await process_one(1, "test_edit_group_abc123")

    assert captured_status.get("status") == "queued"


def test_process_upload_requeues_with_escalating_delays_on_storage_error():
    """process_upload retries StorageError with delays of 5, 10, 15 minutes."""
    assert STORAGE_ERROR_DELAYS == [300, 600, 900]

    for retry_num, expected_delay in enumerate(STORAGE_ERROR_DELAYS):
        mock_self = MagicMock()
        mock_self.request.retries = retry_num
        mock_self.retry.side_effect = Exception("retry scheduled")

        with patch(
            "curator.workers.tasks.process_one",
            side_effect=StorageError(_UPLOADSTASH_EXCEPTION_ERROR),
        ):
            with pytest.raises(Exception, match="retry scheduled"):
                process_upload._orig_run.__func__(mock_self, 1, "abc")

        mock_self.retry.assert_called_once_with(
            countdown=expected_delay, exc=mock_self.retry.call_args[1]["exc"]
        )


def test_process_upload_fails_permanently_after_max_storage_retries(mock_session):
    """process_upload marks upload as FAILED after exhausting all StorageError retries."""
    mock_self = MagicMock()
    mock_self.request.retries = len(STORAGE_ERROR_DELAYS)

    captured_status = {}

    def capture_status(session, upload_id, status, **kwargs):
        captured_status["status"] = status

    with (
        patch(
            "curator.workers.tasks.process_one",
            side_effect=StorageError(_UPLOADSTASH_EXCEPTION_ERROR),
        ),
        patch("curator.workers.tasks.get_session") as mock_get_session,
        patch("curator.workers.tasks.update_upload_status", side_effect=capture_status),
    ):
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = process_upload._orig_run.__func__(mock_self, 1, "abc")

    assert result is False
    assert captured_status.get("status") == "failed"
    mock_self.retry.assert_not_called()

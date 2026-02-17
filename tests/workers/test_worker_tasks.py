"""Tests for successful worker task processing."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from curator.app.crypto import encrypt_access_token
from curator.app.models import UploadRequest
from curator.workers.ingest import process_one


@pytest.fixture(autouse=True)
def patch_ingest_get_session(patch_get_session):
    return patch_get_session("curator.workers.ingest.get_session")


@pytest.mark.asyncio
async def test_worker_process_one_decrypts_token(
    mocker, mock_session, mock_isolated_site
):
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

    with (
        patch("curator.workers.ingest.get_upload_request_by_id", return_value=item),
        patch("curator.workers.ingest.update_upload_status"),
        patch("curator.workers.ingest.create_mediawiki_client") as mock_client_patch,
        patch(
            "curator.workers.ingest.upload_file_chunked",
            return_value={
                "result": "success",
                "title": "File.jpg",
                "url": "https://example.com/photo",
            },
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
        mock_client = mocker.MagicMock()
        mock_client.check_title_blacklisted.return_value = (False, "")
        mock_client_patch.return_value = mock_client

        ok = await process_one(1, "test_edit_group_abc123")
        assert ok is True


def test_upload_request_access_token_excluded_from_model_dump():
    """Test that access_token is excluded from UploadRequest.model_dump()."""
    upload = UploadRequest(
        id=1,
        batchid=1,
        userid="u",
        status="queued",
        key="img1",
        handler="mapillary",
        collection="seq",
        access_token=("secret", "token"),
        filename="File.jpg",
        wikitext="wikitext",
    )

    dumped = upload.model_dump(mode="json")

    assert "access_token" not in dumped

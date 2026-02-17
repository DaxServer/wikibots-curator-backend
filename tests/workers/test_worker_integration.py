"""Integration tests for worker functionality."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from curator.app.crypto import encrypt_access_token
from curator.workers.ingest import process_one


@pytest.fixture(autouse=True)
def patch_ingest_get_session(patch_get_session):
    return patch_get_session("curator.workers.ingest.get_session")


@pytest.mark.asyncio
async def test_worker_process_one_includes_edit_group_id_in_summary(
    mocker, mock_session, mock_isolated_site
):
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
        captured_edit_summary["summary"] = edit_summary
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
    ):
        mock_client = mocker.MagicMock()
        mock_client.check_title_blacklisted.return_value = (False, "")
        mock_client_patch.return_value = mock_client

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

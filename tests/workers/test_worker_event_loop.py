from unittest.mock import patch

import pytest

from curator.app.models import UploadRequest, User
from curator.asyncapi import (
    CameraInfo,
    Creator,
    Dates,
    GeoLocation,
    ImageDimensions,
    ImageUrls,
    MediaImage,
)
from curator.workers import ingest


@pytest.fixture(autouse=True)
def setup_mock_isolated_site(mocker, mock_isolated_site):
    """Patch create_isolated_site to return the shared mock site"""
    return mocker.patch(
        "curator.workers.ingest.create_isolated_site", return_value=mock_isolated_site
    )


def make_image():
    return MediaImage(
        id="123",
        title="Test",
        dates=Dates(taken="2023-01-01T00:00:00Z"),
        creator=Creator(id="1", username="u", profile_url="p"),
        location=GeoLocation(latitude=0.0, longitude=0.0),
        existing=[],
        urls=ImageUrls(
            original="https://example.com/file.jpg",
            thumbnail="t",
            preview="p",
            url="u",
        ),
        dimensions=ImageDimensions(width=1, height=1),
        camera=CameraInfo(is_pano=False),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("runs", [1, 2])
async def test_process_one_runs_without_event_loop_closed(
    mocker, mock_session, runs, patch_get_session
):
    patch_get_session("curator.workers.ingest.get_session")
    with (
        patch.object(ingest, "get_upload_request_by_id") as mock_get,
        patch.object(ingest, "update_upload_status") as mock_update,
        patch.object(ingest, "clear_upload_access_token") as mock_clear,
        patch.object(ingest, "upload_file_chunked") as mock_upload,
        patch.object(ingest.MapillaryHandler, "fetch_image_metadata") as mock_fetch,
        patch.object(ingest, "decrypt_access_token") as mock_decrypt,
        patch.object(ingest, "create_mediawiki_client") as mock_create_client,
    ):
        mock_decrypt.return_value = "token"
        mock_fetch.return_value = make_image()
        mock_client = mocker.MagicMock()
        mock_client.check_title_blacklisted.return_value = (False, "")
        mock_create_client.return_value = mock_client
        mock_item = UploadRequest(
            id=1,
            batchid=1,
            userid="user",
            status="queued",
            key="123",
            handler="mapillary",
            filename="file.jpg",
            wikitext="wikitext",
            collection="collection",
            access_token="token",
        )
        mock_item.user = User(userid="user", username="user")
        mock_get.return_value = mock_item
        mock_upload.return_value = {"url": "https://commons.example/File:Test.jpg"}

        for _ in range(runs):
            assert await ingest.process_one(1, "test_edit_group_abc123") is True

        assert mock_update.call_count >= 2
        assert mock_clear.call_count >= runs

from unittest.mock import patch

import pytest

from curator.app.models import User
from curator.asyncapi import Creator, Dates, GeoLocation, MediaImage
from curator.workers import ingest


def make_image():
    return MediaImage(
        id="123",
        title="Test",
        dates=Dates(taken="2023-01-01T00:00:00Z"),
        creator=Creator(id="1", username="u", profile_url="p"),
        location=GeoLocation(latitude=0.0, longitude=0.0, compass_angle=0.0),
        existing=[],
        url_original="https://example.com/file.jpg",
        thumbnail_url="t",
        preview_url="p",
        url="u",
        width=1,
        height=1,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("runs", [1, 2])
async def test_process_one_runs_without_event_loop_closed(mocker, mock_session, runs, patch_get_session):
    patch_get_session("curator.workers.ingest.get_session")
    with (
        patch.object(ingest, "get_upload_request_by_id") as mock_get,
        patch.object(ingest, "update_upload_status") as mock_update,
        patch.object(ingest, "check_title_blacklisted", return_value=(False, "")),
        patch.object(ingest, "clear_upload_access_token") as mock_clear,
        patch.object(ingest, "upload_file_chunked") as mock_upload,
        patch.object(ingest.MapillaryHandler, "fetch_image_metadata") as mock_fetch,
        patch.object(ingest, "decrypt_access_token") as mock_decrypt,
    ):
        mock_decrypt.return_value = "token"
        mock_fetch.return_value = make_image()
        mock_item = ingest.UploadRequest(
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
            assert await ingest.process_one(1) is True

        assert mock_update.call_count >= 2
        assert mock_clear.call_count >= runs

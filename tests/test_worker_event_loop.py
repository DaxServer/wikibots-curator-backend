from unittest.mock import MagicMock, patch

import pytest

from curator.app.models import User


def make_image():
    from curator.app.image_models import Creator, Dates, Image, Location

    return Image(
        id="123",
        title="Test",
        dates=Dates(),
        creator=Creator(id="1", username="u", profile_url="p"),
        location=Location(latitude=0.0, longitude=0.0),
        url_original="https://example.com/file.jpg",
        thumbnail_url="t",
        preview_url="p",
        url="u",
        width=1,
        height=1,
    )


@pytest.mark.parametrize("runs", [1, 2])
@pytest.mark.asyncio
async def test_process_one_runs_without_event_loop_closed(runs):
    from curator.workers import ingest

    sess = MagicMock()
    sess.close = MagicMock()

    def fake_session_iter():
        yield sess

    with (
        patch.object(ingest, "get_session", side_effect=fake_session_iter),
        patch.object(ingest, "get_upload_request_by_id") as mock_get,
        patch.object(ingest, "update_upload_status") as mock_update,
        patch.object(ingest, "clear_upload_access_token") as mock_clear,
        patch.object(ingest, "upload_file_chunked") as mock_upload,
        patch.object(ingest.MapillaryHandler, "fetch_image_metadata") as mock_fetch,
        patch.object(ingest, "decrypt_access_token") as mock_decrypt,
    ):
        mock_session = sess

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
        assert mock_session.close.call_count >= runs

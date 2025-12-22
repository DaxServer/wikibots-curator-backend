from unittest.mock import MagicMock, call

import pytest

from curator.workers import ingest as mod


@pytest.mark.asyncio
async def test_process_one_runs_async(mocker):
    # Setup Mocks
    mock_session = MagicMock()
    mocker.patch(
        "curator.workers.ingest.get_session", return_value=iter([mock_session])
    )

    mock_item = MagicMock()
    mock_item.id = 1
    mock_item.batchid = 123
    mock_item.userid = "u1"
    mock_item.key = "img-1"
    mock_item.filename = "Test.jpg"
    mock_item.wikitext = "== Summary =="
    mock_item.sdc = [{"P180": "Q42"}]
    mock_item.labels = {"en": "Test"}
    mock_item.collection = "seq-1"
    mock_item.access_token = "cipher"
    mock_item.user.username = "user1"
    mock_item.status = "queued"

    mocker.patch(
        "curator.workers.ingest.get_upload_request_by_id", return_value=mock_item
    )
    mock_update_status = mocker.patch("curator.workers.ingest.update_upload_status")

    mock_handler_instance = MagicMock()
    mock_image = MagicMock()
    mock_image.id = "img-1"
    mock_image.url_original = "https://example.com/file.jpg"
    # fetch_image_metadata is awaited, so it must be an AsyncMock
    mock_handler_instance.fetch_image_metadata = mocker.AsyncMock(
        return_value=mock_image
    )
    mocker.patch(
        "curator.workers.ingest.MapillaryHandler", return_value=mock_handler_instance
    )

    mocker.patch(
        "curator.workers.ingest.decrypt_access_token", return_value=("token", "secret")
    )
    mocker.patch(
        "curator.workers.ingest.upload_file_chunked",
        return_value={"url": "https://commons.wikimedia.org/wiki/File:Test.jpg"},
    )
    mocker.patch("curator.workers.ingest.clear_upload_access_token")

    # Execute
    ok = await mod.process_one(1)

    # Verify
    assert ok is True
    mock_update_status.assert_has_calls(
        [
            call(mock_session, upload_id=1, status="in_progress"),
            call(
                mock_session,
                upload_id=1,
                status="completed",
                success="https://commons.wikimedia.org/wiki/File:Test.jpg",
            ),
        ]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "failed", "duplicate", "in_progress"])
async def test_process_one_skips_non_queued_items(mocker, status):
    # Setup Mocks
    mock_session = MagicMock()
    mocker.patch(
        "curator.workers.ingest.get_session", return_value=iter([mock_session])
    )

    mock_item = MagicMock()
    mock_item.id = 1
    mock_item.status = status

    mocker.patch(
        "curator.workers.ingest.get_upload_request_by_id", return_value=mock_item
    )
    mock_update_status = mocker.patch("curator.workers.ingest.update_upload_status")
    mock_upload = mocker.patch("curator.workers.ingest.upload_file_chunked")
    mocker.patch("curator.workers.ingest.clear_upload_access_token")

    # Execute
    ok = await mod.process_one(1)

    # Verify
    assert ok is False
    mock_update_status.assert_not_called()
    mock_upload.assert_not_called()
    mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_process_one_missing_access_token(mocker):
    # Setup Mocks
    mock_session = MagicMock()
    mocker.patch(
        "curator.workers.ingest.get_session", return_value=iter([mock_session])
    )

    mock_item = MagicMock()
    mock_item.id = 1
    mock_item.status = "queued"
    mock_item.access_token = None  # Missing token
    mock_item.key = "img-1"
    mock_item.collection = "seq-1"
    mock_item.sdc = None

    mocker.patch(
        "curator.workers.ingest.get_upload_request_by_id", return_value=mock_item
    )
    mock_update_status = mocker.patch("curator.workers.ingest.update_upload_status")

    mock_handler_instance = MagicMock()
    mock_image = MagicMock()
    mock_image.id = "img-1"
    mock_image.url_original = "https://example.com/file.jpg"
    mock_handler_instance.fetch_image_metadata = mocker.AsyncMock(
        return_value=mock_image
    )
    mocker.patch(
        "curator.workers.ingest.MapillaryHandler", return_value=mock_handler_instance
    )

    mocker.patch("curator.workers.ingest.clear_upload_access_token")

    # Execute
    ok = await mod.process_one(1)

    # Verify
    assert ok is False
    mock_update_status.assert_has_calls(
        [
            call(mock_session, upload_id=1, status="in_progress"),
            call(
                mock_session,
                upload_id=1,
                status="failed",
                error={"type": "error", "message": "Missing access token"},
            ),
        ]
    )

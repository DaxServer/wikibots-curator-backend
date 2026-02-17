"""Tests for async operations in ingestion worker."""

from unittest.mock import call

import pytest

from curator.asyncapi import GenericError
from curator.workers.ingest import process_one


@pytest.fixture(autouse=True)
def patch_ingest_get_session(patch_get_session):
    return patch_get_session("curator.workers.ingest.get_session")


@pytest.mark.asyncio
async def test_process_one_runs_async(
    mocker,
    patch_get_upload_request_by_id,
    patch_update_upload_status,
    patch_mapillary_handler,
    patch_decrypt_access_token,
    patch_check_title_blacklisted,
    patch_upload_file_chunked,
    patch_clear_upload_access_token,
    mock_session,
    mock_upload_request,
):
    # Execute
    ok = await process_one(1, "test_edit_group_abc123")

    # Verify
    assert ok is True
    patch_update_upload_status.assert_has_calls(
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
async def test_process_one_skips_non_queued_items(
    mocker,
    patch_get_upload_request_by_id,
    patch_update_upload_status,
    patch_clear_upload_access_token,
    mock_session,
    mock_upload_request,
    status,
):
    # Setup - modify the mock upload request status
    mock_upload_request.status = status

    # Execute
    ok = await process_one(1, "test_edit_group_abc123")

    # Verify
    assert ok is False
    patch_update_upload_status.assert_not_called()
    # session is closed by get_session context manager
    assert mock_session.close.call_count >= 1


@pytest.mark.asyncio
async def test_process_one_missing_access_token(
    mocker,
    patch_get_upload_request_by_id,
    patch_update_upload_status,
    patch_mapillary_handler,
    patch_clear_upload_access_token,
    mock_session,
    mock_upload_request,
):
    # Setup - modify the mock upload request to have no access token
    mock_upload_request.access_token = None
    mock_upload_request.sdc = None

    # Execute
    ok = await process_one(1, "test_edit_group_abc123")

    # Verify
    assert ok is False
    patch_update_upload_status.assert_has_calls(
        [
            call(mock_session, upload_id=1, status="in_progress"),
            call(
                mock_session,
                upload_id=1,
                status="failed",
                error=GenericError(type="error", message="Missing access token"),
            ),
        ]
    )

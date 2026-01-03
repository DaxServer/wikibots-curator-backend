from typing import Any, cast

import pytest

from curator.app.dal import (
    create_upload_requests_for_batch,
    get_batch,
    get_upload_request_by_id,
    reset_failed_uploads,
)
from curator.app.models import UploadItem, UploadRequest
from curator.asyncapi import GeoLocation, SdcV2


def test_get_upload_request_by_id(mocker, mock_session):
    """Test that get_upload_request_by_id works with integer ID"""
    # Create a mock UploadRequest
    mock_upload_request = mocker.MagicMock()
    mock_upload_request.id = 123
    mock_upload_request.batchid = 456
    mock_upload_request.filename = "test.jpg"

    # Configure the mock session to return our mock upload request
    mock_session.get.return_value = mock_upload_request

    # Execute
    result = get_upload_request_by_id(mock_session, 123)

    # Verify
    assert result == mock_upload_request
    mock_session.get.assert_called_once_with(UploadRequest, 123)


def test_get_upload_request_by_id_not_found(mock_session):
    """Test that get_upload_request_by_id returns None when not found"""
    # Configure the mock session to return None
    mock_session.get.return_value = None

    # Execute
    result = get_upload_request_by_id(mock_session, 456)

    # Verify
    assert result is None
    mock_session.get.assert_called_once_with(UploadRequest, 456)


def test_get_batch(mocker, mock_session):
    """Test that get_batch works with integer ID"""
    # Create a mock Batch with proper attributes
    mock_batch = mocker.MagicMock()
    mock_batch.id = 789
    mock_batch.userid = "user123"
    mock_batch.name = "Test Batch"
    mock_batch.created_at.isoformat.return_value = "2023-01-01T00:00:00"

    # Create mock user
    mock_user = mocker.MagicMock()
    mock_user.username = "testuser"
    mock_batch.user = mock_user

    # Configure the mock session to return our mock batch
    mock_session.exec.return_value.first.return_value = mock_batch
    mock_session.exec.return_value.all.return_value = []

    # Execute
    result = get_batch(mock_session, 789)

    # Verify
    assert result is not None
    assert result.id == 789
    assert result.userid == "user123"
    assert result.username == "testuser"
    # get_batch calls exec twice - once for batch query, once for stats
    assert mock_session.exec.call_count == 2


def test_get_batch_not_found(mock_session):
    """Test that get_batch returns None when not found"""
    # Configure the mock session to return None
    mock_session.exec.return_value.first.return_value = None

    # Execute
    result = get_batch(mock_session, 999)

    # Verify
    assert result is None
    mock_session.exec.assert_called_once()


def test_reset_failed_uploads_success(mocker, mock_session):
    """Test successful reset of failed uploads"""
    # Create mock batch
    mock_batch = mocker.MagicMock()
    mock_batch.userid = "user1"
    mock_session.get.return_value = mock_batch

    # Create mock failed uploads
    mock_upload1 = mocker.MagicMock()
    mock_upload1.id = 1
    mock_upload1.status = "failed"
    mock_upload1.error = "some error"
    mock_upload1.result = "some result"

    mock_upload2 = mocker.MagicMock()
    mock_upload2.id = 2
    mock_upload2.status = "failed"

    mock_session.exec.return_value.all.return_value = [mock_upload1, mock_upload2]

    # Execute
    result = reset_failed_uploads(mock_session, 123, "user1", "encrypted_token")

    # Verify
    assert len(result) == 2
    assert result == [1, 2]
    assert mock_upload1.status == "queued"
    assert mock_upload1.error is None
    assert mock_upload1.result is None
    assert mock_upload1.access_token == "encrypted_token"
    assert mock_upload2.status == "queued"
    assert mock_upload2.access_token == "encrypted_token"
    mock_session.commit.assert_called_once()


def test_reset_failed_uploads_not_found(mock_session):
    """Test reset_failed_uploads when batch not found"""
    mock_session.get.return_value = None

    # Execute and verify exception
    with pytest.raises(ValueError, match="Batch not found"):
        reset_failed_uploads(mock_session, 123, "user1", "encrypted_token")


def test_reset_failed_uploads_forbidden(mocker, mock_session):
    """Test reset_failed_uploads when user doesn't have permission"""
    # Create mock batch with different user
    mock_batch = mocker.MagicMock()
    mock_batch.userid = "other_user"
    mock_session.get.return_value = mock_batch

    # Execute and verify exception
    with pytest.raises(PermissionError, match="Permission denied"):
        reset_failed_uploads(mock_session, 123, "user1", "encrypted_token")


def test_create_upload_requests_for_batch_persists_sdc_v2(mock_session):
    sdc_v2 = SdcV2(
        type="mapillary",
        version=1,
        creator_username="alice",
        mapillary_image_id="168951548443095",
        taken_at="2023-01-01T00:00:00Z",
        source_url="https://example.com/photo",
        location=GeoLocation(latitude=52.52, longitude=13.405, compass_angle=123.45),
        width=1920,
        height=1080,
        include_default_copyright=True,
    )

    item = UploadItem(
        id="img1",
        input="seq1",
        title="Test Image",
        wikitext="Some wikitext",
        sdc=[],
        sdc_v2=sdc_v2,
    )

    reqs = create_upload_requests_for_batch(
        session=mock_session,
        userid="user123",
        username="testuser",
        batchid=1,
        payload=[item],
        handler="mapillary",
        encrypted_access_token="encrypted_token",
    )

    assert len(reqs) == 1
    assert reqs[0].sdc_v2 is not None
    sdc_v2_data = cast(dict[str, Any], reqs[0].sdc_v2)
    assert sdc_v2_data["version"] == 1
    assert sdc_v2_data["creator_username"] == "alice"

    mock_session.add.assert_called()
    mock_session.commit.assert_called_once()

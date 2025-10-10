"""Test for the mapillary upload fix"""

import pytest
from unittest.mock import Mock, patch
from curator.workers.mapillary import process_one
from curator.app.models import UploadRequest


def test_process_one_with_none_upload_id():
    """Test that process_one handles None upload_id gracefully"""
    # Test with None upload_id
    result = process_one(None, "test_access_token")
    assert result is False


def test_process_one_with_dict_upload_id():
    """Test that process_one handles dictionary upload_id (the bug case)"""
    # This should fail gracefully when a dict is passed instead of an int
    result = process_one({"id": 123, "key": "test"}, "test_access_token")
    assert result is False


def test_process_one_with_valid_upload_id():
    """Test that process_one works with valid upload_id"""
    # Create a mock session
    mock_session = Mock()

    # Create a mock UploadRequest
    mock_upload_request = Mock(spec=UploadRequest)
    mock_upload_request.id = 123
    mock_upload_request.key = "test_key"
    mock_upload_request.userid = "test_user"
    mock_upload_request.batch_id = "test_batch"
    mock_upload_request.filename = "test.jpg"
    mock_upload_request.wikitext = "test wikitext"

    # Mock the database functions
    with patch(
        "curator.workers.mapillary.get_upload_request_by_id",
        return_value=mock_upload_request,
    ):
        with patch("curator.workers.mapillary.update_upload_status"):
            with patch(
                "curator.workers.mapillary.fetch_image_metadata",
                return_value={"test": "data"},
            ):
                with patch(
                    "curator.workers.mapillary.build_mapillary_sdc",
                    return_value={"sdc": "data"},
                ):
                    with patch(
                        "curator.workers.mapillary.upload_file_chunked",
                        return_value={"result": "success"},
                    ):
                        with patch(
                            "curator.workers.mapillary.count_open_uploads_for_batch"
                        ):
                            with patch(
                                "curator.workers.mapillary.get_session",
                                return_value=iter([mock_session]),
                            ):
                                result = process_one(123, "test_access_token")
                                assert result is True


def test_process_one_with_missing_upload():
    """Test that process_one handles missing upload request"""
    # Mock the database functions
    with patch("curator.workers.mapillary.get_upload_request_by_id", return_value=None):
        result = process_one(999, "test_access_token")
        assert result is False

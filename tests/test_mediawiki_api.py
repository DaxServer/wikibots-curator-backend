"""Tests for MediaWiki API request handling"""

from unittest.mock import mock_open, patch

import pytest
from mwoauth import AccessToken

from curator.app.errors import DuplicateUploadError
from curator.app.mediawiki_client import MediaWikiClient


def test_check_title_blacklisted_returns_false_for_clean_title(mocker):
    """Test that check_title_blacklisted returns (False, '') for clean title"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "titleblacklist": {
                "result": "ok",
            }
        }
    )

    result = mock_client.check_title_blacklisted("Clean_Title.jpg")

    assert result == (False, "")
    mock_client._api_request.assert_called_once_with(
        {
            "action": "titleblacklist",
            "tbaction": "create",
            "tbtitle": "File:Clean_Title.jpg",
        }
    )


def test_check_title_blacklisted_returns_true_for_blacklisted_title(mocker):
    """Test that check_title_blacklisted returns (True, reason) for blacklisted title"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "titleblacklist": {
                "result": "blacklisted",
                "reason": "Promotional content",
            }
        }
    )

    result = mock_client.check_title_blacklisted("Spam_Promo.jpg")

    assert result == (True, "Promotional content")


def test_check_title_blacklisted_returns_false_on_api_error(mocker):
    """Test that check_title_blacklisted returns (False, '') on API error"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(side_effect=Exception("API timeout"))

    result = mock_client.check_title_blacklisted("Error_Title.jpg")

    assert result == (False, "")


def test_check_title_blacklisted_default_reason(mocker):
    """Test that check_title_blacklisted uses default reason when none provided"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "titleblacklist": {
                "result": "blacklisted",
            }
        }
    )

    result = mock_client.check_title_blacklisted("Bad_Title.jpg")

    assert result == (True, "Title is blacklisted")


def test_get_csrf_token_returns_string(mocker):
    """Test that get_csrf_token returns string token"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={"query": {"tokens": {"csrftoken": "test-csrf-token-123\\+\\"}}}
    )

    result = mock_client.get_csrf_token()

    assert isinstance(result, str)
    assert result == "test-csrf-token-123\\+\\"
    mock_client._api_request.assert_called_once_with(
        {"action": "query", "meta": "tokens", "type": "csrf"}
    )


def test_get_csrf_token_handles_api_error(mocker):
    """Test that get_csrf_token raises exception on API error"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(side_effect=Exception("API timeout"))

    with pytest.raises(Exception, match="API timeout"):
        mock_client.get_csrf_token()


def test_upload_file_returns_success_when_final_chunk_returns_success(mocker):
    """Test that upload_file returns success when final chunk returns 'Success'"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client.get_csrf_token = mocker.MagicMock(return_value="test-token")

    final_chunk_response = {
        "upload": {
            "result": "Success",
            "filename": "Test.jpg",
            "imageinfo": {
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Test.jpg"
            },
        }
    }

    mock_client._api_request = mocker.MagicMock(return_value=final_chunk_response)

    with (
        patch("os.path.getsize", return_value=1000),
        patch("builtins.open", mock_open(read_data=b"test data")),
    ):
        result = mock_client.upload_file(
            filename="Test.jpg",
            file_path="/tmp/test.jpg",
            wikitext="== Summary ==",
            edit_summary="Test upload",
        )

    assert result.success is True
    assert result.title == "Test.jpg"
    assert result.url == "https://commons.wikimedia.org/wiki/File:Test.jpg"


def test_upload_file_raises_duplicate_error_when_warnings_duplicate(mocker):
    """Test that upload_file raises DuplicateUploadError when API returns duplicate warnings"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client.get_csrf_token = mocker.MagicMock(return_value="test-token")

    final_chunk_response = {
        "upload": {
            "result": "Success",
            "filename": "Test.jpg",
            "warnings": {
                "duplicate": ["File:Existing_File_1.jpg", "File:Existing_File_2.jpg"]
            },
            "imageinfo": {
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Test.jpg"
            },
        }
    }

    mock_client._api_request = mocker.MagicMock(return_value=final_chunk_response)

    with (
        patch("os.path.getsize", return_value=1000),
        patch("builtins.open", mock_open(read_data=b"test data")),
    ):
        with pytest.raises(DuplicateUploadError) as exc_info:
            mock_client.upload_file(
                filename="Test.jpg",
                file_path="/tmp/test.jpg",
                wikitext="== Summary ==",
                edit_summary="Test upload",
            )

    assert len(exc_info.value.duplicates) == 2
    assert exc_info.value.duplicates[0].title == "File:Existing_File_1.jpg"
    assert exc_info.value.duplicates[1].title == "File:Existing_File_2.jpg"


def test_upload_file_fails_when_other_warnings(mocker):
    """Test that upload_file returns failure when API returns non-duplicate warnings"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client.get_csrf_token = mocker.MagicMock(return_value="test-token")

    final_chunk_response = {
        "upload": {
            "result": "Success",
            "filename": "Test.jpg",
            "warnings": {"exists": "File:Test.jpg"},
            "imageinfo": {
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Test.jpg"
            },
        }
    }

    mock_client._api_request = mocker.MagicMock(return_value=final_chunk_response)

    with (
        patch("os.path.getsize", return_value=1000),
        patch("builtins.open", mock_open(read_data=b"test data")),
    ):
        result = mock_client.upload_file(
            filename="Test.jpg",
            file_path="/tmp/test.jpg",
            wikitext="== Summary ==",
            edit_summary="Test upload",
        )

    assert result.success is False
    assert result.error is not None and "warnings" in result.error

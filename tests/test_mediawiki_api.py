"""Tests for MediaWiki API request handling"""

from unittest.mock import MagicMock, patch

import pytest
import requests
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


def _mock_api_request_for_success(
    params, method="GET", data=None, files=None, timeout=300.0
):
    """Helper function that returns appropriate responses based on request parameters"""
    # CSRF token request
    if params.get("action") == "query":
        return {"query": {"tokens": {"csrftoken": "test-token"}}}

    # Chunk upload with stash=1 returns stashed result (NO warnings)
    if data and data.get("stash") == "1":
        return {
            "upload": {
                "result": "Success",
                "filekey": "test-filekey-abc123",
                "canonicaltitle": "File:20260220163823!chunkedupload e744fe49c65b.jpg",
            }
        }

    # Final commit (no stash parameter) returns FINAL filename
    if data and data.get("filekey") and not data.get("stash"):
        return {
            "upload": {
                "result": "Success",
                "filename": "Test.jpg",
                "imageinfo": {
                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Test.jpg"
                },
            }
        }

    return {}


def test_upload_file_returns_success_when_final_chunk_returns_success(mocker):
    """Test that upload_file returns success after chunked upload with final commit"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        side_effect=_mock_api_request_for_success
    )

    # Create a mock file object that supports seeking
    mock_file = MagicMock()
    mock_file.read.return_value = b"test data"
    mock_file.__enter__ = MagicMock(return_value=mock_file)
    mock_file.__exit__ = MagicMock(return_value=False)

    with (
        patch("os.path.getsize", return_value=1000),
        patch("builtins.open", return_value=mock_file),
    ):
        result = mock_client.upload_file(
            filename="Test.jpg",
            file_path="/tmp/test.jpg",
            wikitext="== Summary ==",
            edit_summary="Test upload",
        )

    # Verify final commit was called by checking call count
    # Should have 3 calls: csrf token, chunk stash, final commit
    assert mock_client._api_request.call_count == 3

    # Verify the third call (final commit) had filekey but no stash
    third_call_data = mock_client._api_request.call_args_list[2][1]["data"]
    assert third_call_data.get("filekey") == "test-filekey-abc123"
    assert third_call_data.get("stash") is None

    assert result.success is True
    assert result.title == "Test.jpg"
    assert result.url == "https://commons.wikimedia.org/wiki/File:Test.jpg"


def _mock_api_request_for_duplicate(
    params, method="GET", data=None, files=None, timeout=300.0
):
    """Helper function that returns duplicate warning on chunk upload"""
    # CSRF token request
    if params.get("action") == "query":
        return {"query": {"tokens": {"csrftoken": "test-token"}}}

    # Chunk upload with stash=1 returns duplicate warnings
    if data and data.get("stash") == "1":
        return {
            "upload": {
                "result": "Success",
                "filekey": "test-filekey-abc123",
                "canonicaltitle": "File:20260220163823!chunkedupload e744fe49c65b.jpg",
                "warnings": {
                    "duplicate": ["Existing_File_1.jpg", "Existing_File_2.jpg"]
                },
            }
        }

    return {}


def test_upload_file_raises_duplicate_error_when_warnings_duplicate(mocker):
    """Test that upload_file raises DuplicateUploadError when final chunk returns duplicate warnings"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        side_effect=_mock_api_request_for_duplicate
    )

    mock_file = MagicMock()
    mock_file.read.return_value = b"test data"
    mock_file.__enter__ = MagicMock(return_value=mock_file)
    mock_file.__exit__ = MagicMock(return_value=False)

    with (
        patch("os.path.getsize", return_value=1000),
        patch("builtins.open", return_value=mock_file),
    ):
        with pytest.raises(DuplicateUploadError) as exc_info:
            mock_client.upload_file(
                filename="Test.jpg",
                file_path="/tmp/test.jpg",
                wikitext="== Summary ==",
                edit_summary="Test upload",
            )

    # Verify final commit was NOT called (only 2 calls: csrf + chunk)
    assert mock_client._api_request.call_count == 2

    assert len(exc_info.value.duplicates) == 2
    assert exc_info.value.duplicates[0].title == "Existing_File_1.jpg"
    assert exc_info.value.duplicates[1].title == "Existing_File_2.jpg"


def _mock_api_request_for_warnings(
    params, method="GET", data=None, files=None, timeout=300.0
):
    """Helper function that returns non-duplicate warning on chunk upload"""
    # CSRF token request
    if params.get("action") == "query":
        return {"query": {"tokens": {"csrftoken": "test-token"}}}

    # Chunk upload with stash=1 returns non-duplicate warnings
    if data and data.get("stash") == "1":
        return {
            "upload": {
                "result": "Success",
                "filekey": "test-filekey-abc123",
                "canonicaltitle": "File:20260220163823!chunkedupload e744fe49c65b.jpg",
                "warnings": {"exists": "File:Test.jpg"},
            }
        }

    return {}


def test_upload_file_fails_when_other_warnings(mocker):
    """Test that upload_file returns failure when final chunk returns non-duplicate warnings"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        side_effect=_mock_api_request_for_warnings
    )

    mock_file = MagicMock()
    mock_file.read.return_value = b"test data"
    mock_file.__enter__ = MagicMock(return_value=mock_file)
    mock_file.__exit__ = MagicMock(return_value=False)

    with (
        patch("os.path.getsize", return_value=1000),
        patch("builtins.open", return_value=mock_file),
    ):
        result = mock_client.upload_file(
            filename="Test.jpg",
            file_path="/tmp/test.jpg",
            wikitext="== Summary ==",
            edit_summary="Test upload",
        )

    # Verify final commit was NOT called (only 2 calls: csrf + chunk)
    assert mock_client._api_request.call_count == 2

    assert result.success is False
    assert result.error is not None and "warnings" in result.error


# Tests for retry functionality with exponential backoff


def test_api_request_succeeds_on_first_attempt_no_retry(mocker):
    """Test that API request succeeds immediately when retry=False (default)"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True}
    mock_client._client.request = MagicMock(return_value=mock_response)

    result = mock_client._api_request({"action": "test"})

    assert result == {"success": True}
    mock_client._client.request.assert_called_once()


def test_api_request_succeeds_on_first_attempt_with_retry(mocker):
    """Test that API request succeeds immediately when retry=True"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True}
    mock_client._client.request = MagicMock(return_value=mock_response)
    mock_sleep = mocker.patch("time.sleep")

    result = mock_client._api_request({"action": "test"}, retry=True)

    assert result == {"success": True}
    mock_client._client.request.assert_called_once()
    mock_sleep.assert_not_called()


def test_api_request_succeeds_after_first_retry(mocker):
    """Test that API request succeeds after first retry with 1s backoff"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True}
    mock_client._client.request = MagicMock(
        side_effect=[
            requests.exceptions.RequestException("Network error"),
            mock_response,
        ]
    )
    mock_sleep = mocker.patch("time.sleep")

    result = mock_client._api_request({"action": "test"}, retry=True)

    assert result == {"success": True}
    assert mock_client._client.request.call_count == 2
    # Verify sleep was called with 1s backoff
    mock_sleep.assert_called_once_with(1)


def test_api_request_succeeds_after_second_retry(mocker):
    """Test that API request succeeds after second retry with 1s then 3s backoff"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True}
    mock_client._client.request = MagicMock(
        side_effect=[
            requests.exceptions.RequestException("Network error"),
            requests.exceptions.RequestException("Network error"),
            mock_response,
        ]
    )
    mock_sleep = mocker.patch("time.sleep")

    result = mock_client._api_request({"action": "test"}, retry=True)

    assert result == {"success": True}
    assert mock_client._client.request.call_count == 3
    # Verify sleep was called with 1s then 3s backoff
    assert mock_sleep.call_args_list == [mocker.call(1), mocker.call(3)]


def test_api_request_fails_after_all_retries(mocker):
    """Test that API request raises exception after all retries exhausted"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._client.request = MagicMock(
        side_effect=requests.exceptions.RequestException("Network error")
    )
    mock_sleep = mocker.patch("time.sleep")

    with pytest.raises(requests.exceptions.RequestException, match="Network error"):
        mock_client._api_request({"action": "test"}, retry=True)

    # Should have attempted 3 times total
    assert mock_client._client.request.call_count == 3
    # Verify sleep was called with 1s then 3s backoff
    assert mock_sleep.call_args_list == [mocker.call(1), mocker.call(3)]


def test_only_request_exception_triggers_retry(mocker):
    """Test that only RequestException triggers retry, other exceptions propagate immediately"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._client.request = MagicMock(side_effect=ValueError("Non-request error"))
    mock_sleep = mocker.patch("time.sleep")

    with pytest.raises(ValueError, match="Non-request error"):
        mock_client._api_request({"action": "test"}, retry=True)

    # Should only attempt once (no retry for non-RequestException)
    assert mock_client._client.request.call_count == 1
    mock_sleep.assert_not_called()


def test_retry_false_means_no_retry_on_failure(mocker):
    """Test that retry=False (default) means no retry on failure"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._client.request = MagicMock(
        side_effect=requests.exceptions.RequestException("Network error")
    )
    mock_sleep = mocker.patch("time.sleep")

    with pytest.raises(requests.exceptions.RequestException, match="Network error"):
        mock_client._api_request({"action": "test"}, retry=False)

    # Should only attempt once when retry=False
    assert mock_client._client.request.call_count == 1
    mock_sleep.assert_not_called()

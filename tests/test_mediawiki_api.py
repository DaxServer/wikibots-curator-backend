"""Tests for MediaWiki API request handling"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from curator.core.errors import DuplicateUploadError


def test_check_title_blacklisted_returns_false_for_clean_title(
    mediawiki_client, mocker
):
    """Test that check_title_blacklisted returns (False, '') for clean title"""
    mock_client = mediawiki_client
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


def test_check_title_blacklisted_returns_true_for_blacklisted_title(
    mediawiki_client, mocker
):
    """Test that check_title_blacklisted returns (True, reason) for blacklisted title"""
    mock_client = mediawiki_client
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


def test_check_title_blacklisted_returns_false_on_api_error(mediawiki_client, mocker):
    """Test that check_title_blacklisted returns (False, '') on API error"""
    mock_client = mediawiki_client
    mock_client._api_request = mocker.MagicMock(side_effect=Exception("API timeout"))

    result = mock_client.check_title_blacklisted("Error_Title.jpg")

    assert result == (False, "")


def test_check_title_blacklisted_default_reason(mediawiki_client, mocker):
    """Test that check_title_blacklisted uses default reason when none provided"""
    mock_client = mediawiki_client
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "titleblacklist": {
                "result": "blacklisted",
            }
        }
    )

    result = mock_client.check_title_blacklisted("Bad_Title.jpg")

    assert result == (True, "Title is blacklisted")


def test_get_csrf_token_raises_request_exception_when_query_key_missing(
    mediawiki_client, mocker
):
    """get_csrf_token raises RequestException (not KeyError) when API returns error response without 'query'"""
    mock_client = mediawiki_client
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "error": {"code": "internal_api_error_DBQueryError", "info": "transient"}
        }
    )

    with pytest.raises(requests.exceptions.RequestException):
        mock_client.get_csrf_token()


def test_api_request_retries_when_csrf_token_fetch_fails(mediawiki_client, mocker):
    """csrf=True request retries the full attempt (including fresh CSRF token) when token fetch raises RequestException"""
    mock_client = mediawiki_client

    success_response = MagicMock()
    success_response.json.return_value = {"edit": {"result": "Success"}}

    mocker.patch.object(mock_client._client, "request", return_value=success_response)
    mock_get_csrf = mocker.patch.object(
        mock_client,
        "get_csrf_token",
        side_effect=[
            requests.exceptions.RequestException(
                "CSRF token request returned unexpected response"
            ),
            "valid-token-second",
        ],
    )
    mocker.patch("time.sleep")

    result = mock_client._api_request({"action": "edit"}, method="POST", csrf=True)

    assert result == {"edit": {"result": "Success"}}
    assert mock_get_csrf.call_count == 2


def test_get_csrf_token_returns_string(mediawiki_client, mocker):
    """Test that get_csrf_token returns string token"""
    mock_client = mediawiki_client
    mock_client._api_request = mocker.MagicMock(
        return_value={"query": {"tokens": {"csrftoken": "test-csrf-token-123\\+\\"}}}
    )

    result = mock_client.get_csrf_token()

    assert isinstance(result, str)
    assert result == "test-csrf-token-123\\+\\"
    mock_client._api_request.assert_called_once_with(
        {"action": "query", "meta": "tokens", "type": "csrf"}
    )


def test_get_csrf_token_handles_api_error(mediawiki_client, mocker):
    """Test that get_csrf_token raises exception on API error"""
    mock_client = mediawiki_client
    mock_client._api_request = mocker.MagicMock(side_effect=Exception("API timeout"))

    with pytest.raises(Exception, match="API timeout"):
        mock_client.get_csrf_token()


def _mock_api_request_for_success(
    params, method="GET", data=None, files=None, timeout=300.0, csrf=False
):
    """Helper function that returns appropriate responses based on request parameters"""
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


def test_upload_file_returns_success_when_final_chunk_returns_success(
    mediawiki_client, mocker
):
    """Test that upload_file returns success after chunked upload with final commit"""
    mock_client = mediawiki_client
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
    # Should have 2 calls: chunk stash, final commit (CSRF tokens auto-fetched inside)
    assert mock_client._api_request.call_count == 2

    # Verify the second call (final commit) had filekey but no stash
    second_call_data = mock_client._api_request.call_args_list[1][1]["data"]
    assert second_call_data.get("filekey") == "test-filekey-abc123"
    assert second_call_data.get("stash") is None

    assert result.success is True
    assert result.title == "Test.jpg"
    assert result.url == "https://commons.wikimedia.org/wiki/File:Test.jpg"


def _mock_api_request_for_duplicate(
    params, method="GET", data=None, files=None, timeout=300.0, csrf=False
):
    """Helper function that returns duplicate warning on chunk upload"""
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


def test_upload_file_raises_duplicate_error_when_warnings_duplicate(
    mediawiki_client, mocker
):
    """Test that upload_file raises DuplicateUploadError when final chunk returns duplicate warnings"""
    mock_client = mediawiki_client
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

    # Verify final commit was NOT called (only 1 call: chunk, which raised duplicate)
    assert mock_client._api_request.call_count == 1

    assert len(exc_info.value.duplicates) == 2
    assert exc_info.value.duplicates[0].title == "Existing_File_1.jpg"
    assert exc_info.value.duplicates[1].title == "Existing_File_2.jpg"


def _mock_api_request_for_warnings(
    params, method="GET", data=None, files=None, timeout=300.0, csrf=False
):
    """Helper function that returns non-duplicate warning on chunk upload"""
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


def test_upload_file_fails_when_other_warnings(mediawiki_client, mocker):
    """Test that upload_file returns failure when final chunk returns non-duplicate warnings"""
    mock_client = mediawiki_client
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

    # Verify final commit was NOT called (only 1 call: chunk with warnings)
    assert mock_client._api_request.call_count == 1

    assert result.success is False
    assert result.error is not None and "warnings" in result.error


# Tests for retry functionality with exponential backoff


def test_api_request_succeeds_on_first_attempt(mediawiki_client, mocker):
    """Test that API request succeeds immediately without retry"""
    mock_client = mediawiki_client
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True}
    mock_request = mocker.patch.object(
        mock_client._client, "request", return_value=mock_response
    )
    mock_sleep = mocker.patch("curator.mediawiki.client.time.sleep")

    result = mock_client._api_request({"action": "test"})

    assert result == {"success": True}
    mock_request.assert_called_once()
    mock_sleep.assert_not_called()


def test_api_request_succeeds_after_first_retry(mediawiki_client, mocker):
    """Test that API request succeeds after first retry with 1s backoff"""
    mock_client = mediawiki_client
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True}
    mock_request = mocker.patch.object(
        mock_client._client,
        "request",
        side_effect=[
            requests.exceptions.RequestException("Network error"),
            mock_response,
        ],
    )
    mock_sleep = mocker.patch("time.sleep")

    result = mock_client._api_request({"action": "test"})

    assert result == {"success": True}
    assert mock_request.call_count == 2
    # Verify sleep was called with 1s backoff
    mock_sleep.assert_called_once_with(1)


def test_api_request_succeeds_after_second_retry(mediawiki_client, mocker):
    """Test that API request succeeds after second retry with 1s then 3s backoff"""
    mock_client = mediawiki_client
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True}
    mock_request = mocker.patch.object(
        mock_client._client,
        "request",
        side_effect=[
            requests.exceptions.RequestException("Network error"),
            requests.exceptions.RequestException("Network error"),
            mock_response,
        ],
    )
    mock_sleep = mocker.patch("time.sleep")

    result = mock_client._api_request({"action": "test"})

    assert result == {"success": True}
    assert mock_request.call_count == 3
    # Verify sleep was called with 1s then 3s backoff
    assert mock_sleep.call_args_list == [mocker.call(1), mocker.call(3)]


def test_api_request_fails_after_all_retries(mediawiki_client, mocker):
    """Test that API request raises exception after all retries exhausted"""
    mock_client = mediawiki_client
    mock_request = mocker.patch.object(
        mock_client._client,
        "request",
        side_effect=requests.exceptions.RequestException("Network error"),
    )
    mock_sleep = mocker.patch("time.sleep")

    with pytest.raises(requests.exceptions.RequestException, match="Network error"):
        mock_client._api_request({"action": "test"})

    # Should have attempted 3 times total
    assert mock_request.call_count == 3
    # Verify sleep was called with 1s then 3s backoff
    assert mock_sleep.call_args_list == [mocker.call(1), mocker.call(3)]


def test_only_request_exception_triggers_retry(mediawiki_client, mocker):
    """Test that only RequestException triggers retry, other exceptions propagate immediately"""
    mock_client = mediawiki_client
    mock_request = mocker.patch.object(
        mock_client._client, "request", side_effect=ValueError("Non-request error")
    )
    mock_sleep = mocker.patch("time.sleep")

    with pytest.raises(ValueError, match="Non-request error"):
        mock_client._api_request({"action": "test"})

    # Should only attempt once (no retry for non-RequestException)
    assert mock_request.call_count == 1
    mock_sleep.assert_not_called()


def test_csrf_badtoken_triggers_retry_with_fresh_token(mediawiki_client, mocker):
    """Test that badtoken error retries with a fresh CSRF token"""
    mock_client = mediawiki_client

    badtoken_response = MagicMock()
    badtoken_response.json.return_value = {
        "error": {"code": "badtoken", "info": "Invalid CSRF token."}
    }
    success_response = MagicMock()
    success_response.json.return_value = {"edit": {"result": "Success"}}

    mock_request = mocker.patch.object(
        mock_client._client,
        "request",
        side_effect=[badtoken_response, success_response],
    )
    mock_get_csrf = mocker.patch.object(
        mock_client, "get_csrf_token", side_effect=["token-first", "token-second"]
    )
    mocker.patch("time.sleep")

    result = mock_client._api_request({"action": "edit"}, method="POST", csrf=True)

    assert result == {"edit": {"result": "Success"}}
    assert mock_request.call_count == 2
    # Fresh token fetched on each attempt
    assert mock_get_csrf.call_count == 2


def test_csrf_badtoken_returns_error_if_all_retries_fail(mediawiki_client, mocker):
    """Test that persistent badtoken error is returned after all retries exhausted"""
    mock_client = mediawiki_client

    badtoken_response = MagicMock()
    badtoken_response.json.return_value = {
        "error": {"code": "badtoken", "info": "Invalid CSRF token."}
    }

    mocker.patch.object(mock_client._client, "request", return_value=badtoken_response)
    mocker.patch.object(mock_client, "get_csrf_token", return_value="token")
    mocker.patch("time.sleep")

    result = mock_client._api_request({"action": "edit"}, method="POST", csrf=True)

    assert result["error"]["code"] == "badtoken"


_NONCE_ERROR_RESPONSE = {
    "error": {
        "code": "mwoauth-invalid-authorization",
        "info": "The authorization headers in your request are not valid: Nonce already used: t6OoUQIkzg8nlmLy3FYbpSS4TxTIqP",
    }
}


def test_nonce_error_retries_and_succeeds(mediawiki_client, mocker):
    """Nonce already used error retries automatically and returns success on next attempt"""
    mock_client = mediawiki_client

    nonce_response = MagicMock()
    nonce_response.json.return_value = _NONCE_ERROR_RESPONSE
    success_response = MagicMock()
    success_response.json.return_value = {"success": True}

    mock_request = mocker.patch.object(
        mock_client._client,
        "request",
        side_effect=[nonce_response, success_response],
    )
    mock_sleep = mocker.patch("curator.mediawiki.client.time.sleep")

    result = mock_client._api_request({"action": "test"})

    assert result == {"success": True}
    assert mock_request.call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_nonce_error_returns_error_after_retries_exhausted(mediawiki_client, mocker):
    """Nonce error is returned after all nonce retries are exhausted"""
    mock_client = mediawiki_client

    nonce_response = MagicMock()
    nonce_response.json.return_value = _NONCE_ERROR_RESPONSE

    mocker.patch.object(mock_client._client, "request", return_value=nonce_response)
    mocker.patch("curator.mediawiki.client.time.sleep")

    result = mock_client._api_request({"action": "test"})

    assert result["error"]["code"] == "mwoauth-invalid-authorization"


def test_nonce_error_uses_delays_1_3(mediawiki_client, mocker):
    """Nonce retries sleep 1s then 3s before giving up"""
    mock_client = mediawiki_client

    nonce_response = MagicMock()
    nonce_response.json.return_value = _NONCE_ERROR_RESPONSE

    mocker.patch.object(mock_client._client, "request", return_value=nonce_response)
    mock_sleep = mocker.patch("curator.mediawiki.client.time.sleep")

    mock_client._api_request({"action": "test"})

    calls = [c.args[0] for c in mock_sleep.call_args_list]
    assert calls == [1, 3]


def test_other_mwoauth_errors_not_retried(mediawiki_client, mocker):
    """mwoauth-invalid-authorization without 'Nonce already used' is returned without retry"""
    mock_client = mediawiki_client

    other_mwoauth_response = MagicMock()
    other_mwoauth_response.json.return_value = {
        "error": {
            "code": "mwoauth-invalid-authorization",
            "info": "The authorization headers in your request are not valid: Invalid signature.",
        }
    }

    mock_request = mocker.patch.object(
        mock_client._client, "request", return_value=other_mwoauth_response
    )
    mock_sleep = mocker.patch("curator.mediawiki.client.time.sleep")

    result = mock_client._api_request({"action": "test"})

    assert result["error"]["code"] == "mwoauth-invalid-authorization"
    assert mock_request.call_count == 1
    mock_sleep.assert_not_called()


_USERINFO_RATELIMITS_RESPONSE = {
    "batchcomplete": "",
    "query": {
        "userinfo": {
            "id": 4238209,
            "name": "DaxServer",
            "rights": ["edit", "upload", "patrol"],
            "ratelimits": {
                "move": {
                    "user": {"hits": 8, "seconds": 60},
                    "patroller": {"hits": 32, "seconds": 60},
                },
                "edit": {
                    "user": {"hits": 900, "seconds": 180},
                    "patroller": {"hits": 1500, "seconds": 180},
                },
                "upload": {
                    "user": {"hits": 380, "seconds": 4320},
                    "patroller": {"hits": 999, "seconds": 1},
                },
                "linkpurge": {
                    "user": {"hits": 30, "seconds": 60},
                    "patroller": {"hits": 3000, "seconds": 180},
                },
                "badcaptcha": {"user": {"hits": 30, "seconds": 60}},
                "renderfile": {"user": {"hits": 700, "seconds": 30}},
            },
        }
    },
}


_FETCH_PAGE_RESPONSE: dict[str, Any] = {
    "batchcomplete": True,
    "query": {
        "pages": [
            {
                "pageid": 12345,
                "ns": 6,
                "title": "File:Test.jpg",
                "revisions": [
                    {"slots": {"main": {"content": "== Wikitext ==\n{{Information}}"}}}
                ],
            }
        ]
    },
}


_ERROR_RESPONSE = {
    "error": {"code": "internal_api_error_DBQueryError", "info": "transient"}
}


def test_fetch_page_retries_and_raises_key_error_when_query_always_missing(
    mediawiki_client, mocker
):
    """_fetch_page retries all attempts then raises KeyError and logs when 'query' is always absent"""
    mock_client = mediawiki_client
    mock_client._api_request = mocker.MagicMock(return_value=_ERROR_RESPONSE)
    mock_logger = mocker.patch("curator.mediawiki.client.logger")
    mocker.patch("curator.mediawiki.client.time.sleep")

    with pytest.raises(KeyError, match="query"):
        mock_client._fetch_page("Test.jpg")

    assert mock_client._api_request.call_count == 4  # len(HTTP_RETRY_DELAYS) + 1
    mock_logger.error.assert_called_once()
    assert "Test.jpg" in mock_logger.error.call_args[0][0]
    assert "internal_api_error_DBQueryError" in str(mock_logger.error.call_args)


def test_fetch_page_retries_and_succeeds_when_query_missing_then_present(
    mediawiki_client, mocker
):
    """_fetch_page retries on missing 'query' key and returns page on subsequent success"""
    mock_client = mediawiki_client
    mocker.patch("curator.mediawiki.client.logger")
    mock_sleep = mocker.patch("curator.mediawiki.client.time.sleep")

    mock_client._api_request = mocker.MagicMock(
        side_effect=[_ERROR_RESPONSE, _FETCH_PAGE_RESPONSE]
    )

    result = mock_client._fetch_page("Test.jpg")

    assert result == _FETCH_PAGE_RESPONSE["query"]["pages"][0]
    assert mock_client._api_request.call_count == 2
    mock_sleep.assert_called_once_with(3)


def test_null_edit_succeeds_when_fetch_page_eventually_returns_page(
    mediawiki_client, mocker
):
    """null_edit succeeds after _fetch_page retries internally and returns a valid page"""
    mock_client = mediawiki_client
    mocker.patch("curator.mediawiki.client.logger")
    mocker.patch("curator.mediawiki.client.time.sleep")

    mock_client._api_request = mocker.MagicMock(
        side_effect=[
            _ERROR_RESPONSE,
            _FETCH_PAGE_RESPONSE,
            {"edit": {"result": "Success"}},
        ]
    )

    result = mock_client.null_edit("Test.jpg")

    assert result is True


def test_null_edit_raises_key_error_after_all_retries_exhausted(
    mediawiki_client, mocker
):
    """null_edit propagates KeyError after _fetch_page exhausts all retry attempts"""
    mock_client = mediawiki_client
    mocker.patch("curator.mediawiki.client.logger")
    mock_sleep = mocker.patch("curator.mediawiki.client.time.sleep")

    mock_client._api_request = mocker.MagicMock(return_value=_ERROR_RESPONSE)

    with pytest.raises(KeyError, match="query"):
        mock_client.null_edit("Test.jpg")

    assert mock_client._api_request.call_count == 4  # len(HTTP_RETRY_DELAYS) + 1
    assert mock_sleep.call_args_list == [
        mocker.call(3),
        mocker.call(5),
        mocker.call(10),
    ]


def test_get_user_rate_limits_returns_ratelimits_and_rights(mediawiki_client, mocker):
    """get_user_rate_limits returns (ratelimits, rights) tuple from userinfo API"""
    mock_client = mediawiki_client
    mock_client._api_request = mocker.MagicMock(
        return_value=_USERINFO_RATELIMITS_RESPONSE
    )

    ratelimits, rights = mock_client.get_user_rate_limits()

    assert "upload" in ratelimits
    assert "edit" in ratelimits
    assert ratelimits["upload"]["user"]["hits"] == 380
    assert ratelimits["upload"]["patroller"]["hits"] == 999
    assert ratelimits["edit"]["user"]["seconds"] == 180
    assert "patrol" in rights
    mock_client._api_request.assert_called_once_with(
        {
            "action": "query",
            "meta": "userinfo",
            "uiprop": "ratelimits|rights",
        }
    )

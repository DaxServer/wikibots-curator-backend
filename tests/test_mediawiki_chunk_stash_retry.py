"""Tests for chunk upload retry on UploadStashFileException API errors"""

import pytest
from mwoauth import AccessToken

from curator.app.mediawiki_client import MediaWikiClient

_STASH_ERROR = {
    "error": {
        "code": "internal_api_error-UploadStashFileException",
        "info": 'Could not store upload in the stash (MediaWiki\\Upload\\Exception\\UploadStashFileException): "An unknown error occurred in storage backend."',
    }
}

# Variant seen in prod: info field doesn't mention UploadStashFileException, only the code does
_STASH_ERROR_CODE_ONLY = {
    "error": {
        "code": "internal_api_error-UploadStashFileException",
        "info": 'An unknown error occurred in storage backend "local-swift-codfw".',
    }
}

_CSRF_RESPONSE = {"query": {"tokens": {"csrftoken": "test_token"}}}

_CHUNK_SUCCESS = {"upload": {"result": "Success", "filekey": "key123"}}

_COMMIT_SUCCESS = {
    "upload": {
        "result": "Success",
        "filename": "test.jpg",
        "imageinfo": {
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:test.jpg"
        },
    }
}


def _make_upload_responses(*chunk_responses):
    """Build mock side_effect: CSRF interleaved with provided chunk responses, plus commit"""
    call_idx = {"n": 0}

    def _api_request(*args, **kwargs):
        params = args[0] if args else {}
        if params.get("action") == "query" and params.get("meta") == "tokens":
            return _CSRF_RESPONSE
        resp = chunk_responses[call_idx["n"]]
        call_idx["n"] += 1
        if isinstance(resp, Exception):
            raise resp
        return resp

    return _api_request


def _client_with(mocker, *chunk_responses):
    client = MediaWikiClient(AccessToken("test", "test"))
    client._api_request = mocker.MagicMock(
        side_effect=_make_upload_responses(*chunk_responses)
    )
    return client


@pytest.fixture
def tiny_file(tmp_path):
    f = tmp_path / "test.jpg"
    f.write_bytes(b"x" * 100)
    return str(f)


def test_stash_error_triggers_retry_not_immediate_failure(mocker, tiny_file):
    """Stash error in chunk response retries instead of returning failure immediately"""
    mock_sleep = mocker.patch("curator.app.mediawiki_client.time.sleep")

    client = _client_with(mocker, _STASH_ERROR, _CHUNK_SUCCESS, _COMMIT_SUCCESS)
    result = client.upload_file("test.jpg", tiny_file, "wikitext", "summary")

    assert result.success is True
    mock_sleep.assert_called_once_with(3)


def test_stash_error_succeeds_on_second_attempt(mocker, tiny_file):
    """Upload succeeds when stash error on first attempt, success on second"""
    mocker.patch("curator.app.mediawiki_client.time.sleep")

    client = _client_with(mocker, _STASH_ERROR, _CHUNK_SUCCESS, _COMMIT_SUCCESS)
    result = client.upload_file("test.jpg", tiny_file, "wikitext", "summary")

    assert result.success is True
    assert result.title == "test.jpg"
    assert result.url == "https://commons.wikimedia.org/wiki/File:test.jpg"


def test_stash_error_fails_after_all_retries_exhausted(mocker, tiny_file):
    """Returns failure after all 4 attempts return stash errors"""
    mocker.patch("curator.app.mediawiki_client.time.sleep")

    client = _client_with(
        mocker, _STASH_ERROR, _STASH_ERROR, _STASH_ERROR, _STASH_ERROR
    )
    result = client.upload_file("test.jpg", tiny_file, "wikitext", "summary")

    assert result.success is False
    assert "UploadStashFileException" in result.error


def test_stash_error_code_only_triggers_retry(mocker, tiny_file):
    """Stash error where only the error code (not info) contains UploadStashFileException retries"""
    mock_sleep = mocker.patch("curator.app.mediawiki_client.time.sleep")

    client = _client_with(
        mocker, _STASH_ERROR_CODE_ONLY, _CHUNK_SUCCESS, _COMMIT_SUCCESS
    )
    result = client.upload_file("test.jpg", tiny_file, "wikitext", "summary")

    assert result.success is True
    mock_sleep.assert_called_once_with(3)


def test_stash_error_retry_uses_delays_3_5_10(mocker, tiny_file):
    """Retries sleep for 3, 5, 10 seconds in order before giving up"""
    mock_sleep = mocker.patch("curator.app.mediawiki_client.time.sleep")

    client = _client_with(
        mocker, _STASH_ERROR, _STASH_ERROR, _STASH_ERROR, _STASH_ERROR
    )
    client.upload_file("test.jpg", tiny_file, "wikitext", "summary")

    assert mock_sleep.call_count == 3
    calls = [c.args[0] for c in mock_sleep.call_args_list]
    assert calls == [3, 5, 10]

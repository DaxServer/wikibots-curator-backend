"""Tests for chunk upload retry on UploadStashFileException, UploadChunkFileException, JobQueueError, and backend-fail-internal API errors"""

import pytest
import requests
from mwoauth import AccessToken

from curator.core.errors import DuplicateUploadError
from curator.mediawiki.client import MediaWikiClient

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

# Variant seen in prod (T420956): bare uploadstash-exception code, info contains UploadStashFileException
_STASH_EXCEPTION_CODE = {
    "error": {
        "code": "uploadstash-exception",
        "info": 'Could not store upload in the stash (MediaWiki\\Upload\\Exception\\UploadStashFileException): "Im Speicher-Backend „local-swift-eqiad" ist ein unbekannter Fehler aufgetreten.".',
    }
}

_CHUNK_FILE_ERROR = {
    "error": {
        "code": "internal_api_error-UploadChunkFileException",
        "info": "[c35f530a-fb33-492a-98c8-8b6c4f816a7c] Caught exception of type MediaWiki\\Upload\\Exception\\UploadChunkFileException",
    }
}

_JOB_QUEUE_ERROR = {
    "error": {
        "code": "internal_api_error-JobQueueError",
        "info": "[0955ae00-41e9-4fc6-b968-f8a71184154e] Caught exception of type MediaWiki\\JobQueue\\Exceptions\\JobQueueError",
    }
}

_BACKEND_FAIL_INTERNAL = {
    "error": {
        "code": "backend-fail-internal",
        "info": 'An unknown error occurred in storage backend "local-swift-codfw".',
    }
}

# Seen in prod (T424242): stashfailed code with backend-fail-internal in info (swift storage error during stash)
_STASHFAILED_BACKEND_INTERNAL = {
    "error": {
        "code": "stashfailed",
        "info": "Error storing file in 'mwstore://local-multiwrite/local-temp/1/1a/20260408100112!phpg4nXP5.jpg': backend-fail-internal; local-swift-eqiad",
    }
}

_COMMIT_NOCHANGE = {
    "upload": {
        "result": "Warning",
        "warnings": {
            "exists": "Mapillary_(osmplus_org)_2026-01-27_08H07M14S500_(919357217326871_at_0LaBzsJ8hoFb19uPCWIDKn).jpg",
            "nochange": {"timestamp": "2026-04-05T12:26:04Z"},
        },
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


@pytest.fixture
def mock_sleep(mocker):
    return mocker.patch("curator.mediawiki.client.time.sleep")


# --- Chunk retry tests (error on chunk → retry → success) ---


@pytest.mark.parametrize(
    "error_response, label",
    [
        (_STASH_ERROR, "UploadStashFileException"),
        (_STASH_ERROR_CODE_ONLY, "UploadStashFileException (code only)"),
        (_STASH_EXCEPTION_CODE, "uploadstash-exception"),
        (_CHUNK_FILE_ERROR, "UploadChunkFileException"),
        (_JOB_QUEUE_ERROR, "JobQueueError"),
        (_STASHFAILED_BACKEND_INTERNAL, "stashfailed with backend-fail-internal"),
    ],
    ids=lambda x: x if isinstance(x, str) else "",
)
def test_chunk_error_triggers_retry_and_succeeds(
    mocker, tiny_file, mock_sleep, error_response, label
):
    """Retryable chunk error retries and succeeds on second attempt"""
    client = _client_with(mocker, error_response, _CHUNK_SUCCESS, _COMMIT_SUCCESS)
    result = client.upload_file("test.jpg", tiny_file, "wikitext", "summary")

    assert result.success is True
    assert result.title == "test.jpg"
    assert result.url == "https://commons.wikimedia.org/wiki/File:test.jpg"
    mock_sleep.assert_called_once_with(3)


@pytest.mark.parametrize(
    "error_response, expected_substring",
    [
        (_STASH_ERROR, "UploadStashFileException"),
        (_STASHFAILED_BACKEND_INTERNAL, "backend-fail-internal"),
    ],
    ids=["UploadStashFileException", "stashfailed-backend-fail-internal"],
)
def test_chunk_error_fails_after_all_retries_exhausted(
    mocker, tiny_file, mock_sleep, error_response, expected_substring
):
    """Returns failure after all 4 attempts return chunk errors"""
    client = _client_with(
        mocker, error_response, error_response, error_response, error_response
    )
    result = client.upload_file("test.jpg", tiny_file, "wikitext", "summary")

    assert result.success is False
    assert expected_substring in result.error


def test_stash_error_retry_uses_delays_3_5_10(mocker, tiny_file, mock_sleep):
    """Retries sleep for 3, 5, 10 seconds in order before giving up"""
    client = _client_with(
        mocker, _STASH_ERROR, _STASH_ERROR, _STASH_ERROR, _STASH_ERROR
    )
    client.upload_file("test.jpg", tiny_file, "wikitext", "summary")

    assert mock_sleep.call_count == 3
    calls = [c.args[0] for c in mock_sleep.call_args_list]
    assert calls == [3, 5, 10]


# --- Chunk warning tests (duplicate/exists detection) ---


def test_exists_warning_raises_duplicate_upload_error_when_hashes_match(
    mocker, tiny_file, mock_sleep
):
    """exists warning raises DuplicateUploadError when existing file has the same hash"""
    existing_title = "Mapillary_(rking)_2020-07-23.jpg"
    file_sha1 = "abc123hash"
    exists_warning_response = {
        "upload": {"result": "Warning", "warnings": {"exists": existing_title}}
    }

    client = _client_with(mocker, exists_warning_response)
    mocker.patch.object(client, "get_file_sha1", return_value=file_sha1)

    with pytest.raises(DuplicateUploadError) as exc_info:
        client.upload_file(
            "test.jpg", tiny_file, "wikitext", "summary", file_sha1=file_sha1
        )

    assert len(exc_info.value.duplicates) == 1
    assert exc_info.value.duplicates[0].title == existing_title


def test_exists_warning_returns_failure_when_hashes_differ(
    mocker, tiny_file, mock_sleep
):
    """exists warning returns generic failure when existing file has a different hash (name conflict)"""
    existing_title = "Mapillary_(rking)_2020-07-23.jpg"
    exists_warning_response = {
        "upload": {"result": "Warning", "warnings": {"exists": existing_title}}
    }

    client = _client_with(mocker, exists_warning_response)
    mocker.patch.object(client, "get_file_sha1", return_value="different_hash")

    result = client.upload_file(
        "test.jpg", tiny_file, "wikitext", "summary", file_sha1="our_hash"
    )

    assert result.success is False


# --- Final commit retry tests ---


def test_backend_fail_internal_on_commit_retries_and_succeeds(
    mocker, tiny_file, mock_sleep
):
    """backend-fail-internal on final commit retries instead of returning failure immediately"""
    client = _client_with(
        mocker, _CHUNK_SUCCESS, _BACKEND_FAIL_INTERNAL, _COMMIT_SUCCESS
    )
    result = client.upload_file("test.jpg", tiny_file, "wikitext", "summary")

    assert result.success is True
    mock_sleep.assert_called_once_with(3)


def test_backend_fail_internal_on_commit_fails_after_all_retries_exhausted(
    mocker, tiny_file, mock_sleep
):
    """backend-fail-internal on final commit fails after all retry attempts"""
    client = _client_with(
        mocker,
        _CHUNK_SUCCESS,
        _BACKEND_FAIL_INTERNAL,
        _BACKEND_FAIL_INTERNAL,
        _BACKEND_FAIL_INTERNAL,
        _BACKEND_FAIL_INTERNAL,
    )
    result = client.upload_file("test.jpg", tiny_file, "wikitext", "summary")

    assert result.success is False
    assert "backend-fail-internal" in (result.error or "")


def test_job_queue_error_on_commit_retries_and_succeeds(mocker, tiny_file, mock_sleep):
    """JobQueueError on final commit retries instead of returning failure immediately"""
    client = _client_with(mocker, _CHUNK_SUCCESS, _JOB_QUEUE_ERROR, _COMMIT_SUCCESS)
    result = client.upload_file("test.jpg", tiny_file, "wikitext", "summary")

    assert result.success is True
    mock_sleep.assert_called_once_with(3)


def test_request_exception_on_commit_retries_and_succeeds(
    mocker, tiny_file, mock_sleep
):
    """network error on final commit retries instead of propagating immediately"""
    client = _client_with(
        mocker,
        _CHUNK_SUCCESS,
        requests.exceptions.ConnectionError("connection reset"),
        _COMMIT_SUCCESS,
    )
    result = client.upload_file("test.jpg", tiny_file, "wikitext", "summary")

    assert result.success is True
    mock_sleep.assert_called_once_with(3)


def test_request_exception_on_commit_fails_after_all_retries_exhausted(
    mocker, tiny_file, mock_sleep
):
    """network error on final commit fails after all retry attempts"""
    client = _client_with(
        mocker,
        _CHUNK_SUCCESS,
        requests.exceptions.ConnectionError("connection reset"),
        requests.exceptions.ConnectionError("connection reset"),
        requests.exceptions.ConnectionError("connection reset"),
        requests.exceptions.ConnectionError("connection reset"),
    )
    result = client.upload_file("test.jpg", tiny_file, "wikitext", "summary")

    assert result.success is False
    assert result.error is not None


def test_nochange_warning_on_commit_raises_duplicate_upload_error(
    mocker, tiny_file, mock_sleep
):
    """nochange + exists warning on final commit raises DuplicateUploadError instead of generic failure"""
    client = _client_with(mocker, _CHUNK_SUCCESS, _COMMIT_NOCHANGE)

    with pytest.raises(DuplicateUploadError) as exc_info:
        client.upload_file("test.jpg", tiny_file, "wikitext", "summary")

    assert len(exc_info.value.duplicates) == 1
    assert "919357217326871" in exc_info.value.duplicates[0].title

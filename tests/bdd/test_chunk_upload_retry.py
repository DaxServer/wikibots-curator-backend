"""BDD tests for chunk_upload_retry.feature"""

from pathlib import Path

import pytest
import requests
from mwoauth import AccessToken
from pytest_bdd import given, parsers, scenario, then, when

from curator.app.errors import DuplicateUploadError
from curator.app.mediawiki_client import MediaWikiClient

# Flag to track if default mock should be applied
_use_default_mock = True


# --- Scenarios ---


@scenario(
    "features/chunk_upload_retry.feature", "Chunk upload succeeds on first attempt"
)
def test_chunk_upload_success_first_attempt():
    pass


@scenario(
    "features/chunk_upload_retry.feature", "Chunk upload retries once on 502 error"
)
def test_chunk_upload_retry_on_502():
    pass


@scenario("features/chunk_upload_retry.feature", "Chunk upload fails after max retries")
def test_chunk_upload_fails_after_max_retries():
    pass


@scenario("features/chunk_upload_retry.feature", "Chunk upload retry on timeout")
def test_chunk_upload_retry_on_timeout():
    pass


@scenario(
    "features/chunk_upload_retry.feature", "Duplicate error does not trigger retry"
)
def test_duplicate_error_no_retry():
    pass


# --- GIVENS ---


@pytest.fixture
def mock_access_token():
    """Mock OAuth access token"""
    return AccessToken("test_key", "test_secret")


@pytest.fixture
def mock_client_factory(mock_access_token):
    """Factory to create MediaWikiClient with mocked internal client"""
    client = MediaWikiClient(access_token=mock_access_token)
    return client


@pytest.fixture
def test_file(tmp_path):
    """Create a test file of specified size"""

    def _create_file(size_str: str) -> Path:
        # Parse size string like "3MB" to bytes
        size_map = {
            "MB": 1024 * 1024,
            "KB": 1024,
        }
        num = int("".join(filter(str.isdigit, size_str)))
        unit = "".join(filter(str.isalpha, size_str))
        size_bytes = num * size_map.get(unit, 1)

        file_path = tmp_path / "test.jpg"
        file_path.write_bytes(b"x" * size_bytes)
        return file_path

    return _create_file


@given(
    "a MediaWiki client with valid authentication", target_fixture="mediawiki_client"
)
def mediawiki_client(mock_client_factory):
    return mock_client_factory


@given(
    parsers.parse('a file exists at "{path}" with size {size_str}'),
    target_fixture="test_file_path",
)
def _test_file_size(test_file, path, size_str):
    return str(test_file(size_str))


@given(
    parsers.parse(
        "the API request for chunk {chunk_num:d} fails with 502 error on first attempt"
    )
)
def api_request_chunk_fails_once(mocker):
    """Mock _api_request to fail once for specific chunk, then succeed"""
    global _use_default_mock
    _use_default_mock = False

    chunk_upload_count = {"count": 0}

    def _mock_api_request(*args, **kwargs):
        params = args[0] if args else kwargs.get("params", {})

        # Handle CSRF token requests
        if params.get("action") == "query" and params.get("meta") == "tokens":
            return {"query": {"tokens": {"csrftoken": "test_token"}}}

        # Handle chunk upload requests
        chunk_upload_count["count"] += 1
        # Simulate 502 error on first chunk upload attempt
        if chunk_upload_count["count"] == 2:
            raise requests.exceptions.HTTPError("502 Server Error")

        # Normal successful response
        return {
            "upload": {
                "result": "Success",
                "filekey": "testfilekey.12345.jpg",
            }
        }

    return mocker.patch(
        "curator.app.mediawiki_client.MediaWikiClient._api_request",
        side_effect=_mock_api_request,
        autospec=False,
    )


@given("all API requests for chunk 2 fail with 502 error")
def api_request_chunk_always_fails(mocker):
    """Mock _api_request to always fail for chunk 2"""
    global _use_default_mock
    _use_default_mock = False

    chunk_upload_count = {"count": 0}

    def _mock_api_request(*args, **kwargs):
        params = args[0] if args else kwargs.get("params", {})

        # Handle CSRF token requests
        if params.get("action") == "query" and params.get("meta") == "tokens":
            return {"query": {"tokens": {"csrftoken": "test_token"}}}

        # Handle chunk upload requests
        chunk_upload_count["count"] += 1
        # Chunk 1 succeeds
        if chunk_upload_count["count"] == 1:
            return {
                "upload": {
                    "result": "Success",
                    "filekey": "testfilekey.1.jpg",
                }
            }

        # Chunk 2 fails (all attempts)
        raise requests.exceptions.HTTPError("502 Server Error")

    return mocker.patch(
        "curator.app.mediawiki_client.MediaWikiClient._api_request",
        side_effect=_mock_api_request,
        autospec=False,
    )


@given(
    parsers.parse("the API request for chunk {chunk_num:d} times out on first attempt")
)
def api_request_chunk_times_out(mocker):
    """Mock _api_request to timeout once, then succeed"""
    global _use_default_mock
    _use_default_mock = False

    chunk_upload_count = {"count": 0}

    def _mock_api_request(*args, **kwargs):
        params = args[0] if args else kwargs.get("params", {})

        # Handle CSRF token requests
        if params.get("action") == "query" and params.get("meta") == "tokens":
            return {"query": {"tokens": {"csrftoken": "test_token"}}}

        # Handle chunk upload requests
        chunk_upload_count["count"] += 1
        # Timeout on first chunk upload attempt
        if chunk_upload_count["count"] == 1:
            raise requests.exceptions.Timeout("Connection timed out")

        # Normal successful response
        return {
            "upload": {
                "result": "Success",
                "filekey": "testfilekey.12345.jpg",
            }
        }

    return mocker.patch(
        "curator.app.mediawiki_client.MediaWikiClient._api_request",
        side_effect=_mock_api_request,
        autospec=False,
    )


@given(
    parsers.parse("the API response for chunk {chunk_num:d} contains duplicate warning")
)
def api_request_duplicate_warning(mocker):
    """Mock _api_request to return duplicate warning on chunk 3"""
    global _use_default_mock
    _use_default_mock = False

    chunk_upload_count = {"count": 0}

    def _mock_api_request(*args, **kwargs):
        params = args[0] if args else kwargs.get("params", {})

        # Handle CSRF token requests
        if params.get("action") == "query" and params.get("meta") == "tokens":
            return {"query": {"tokens": {"csrftoken": "test_token"}}}

        # Handle chunk upload requests
        chunk_upload_count["count"] += 1
        # Chunks 1-2 succeed
        if chunk_upload_count["count"] < 3:
            return {
                "upload": {
                    "result": "Success",
                    "filekey": "testfilekey.12345.jpg",
                }
            }

        # Chunk 3 has duplicate warning
        return {
            "upload": {
                "result": "Success",
                "filekey": "testfilekey.final.jpg",
                "warnings": {"duplicate": ["File:Existing.jpg"]},
            }
        }

    return mocker.patch(
        "curator.app.mediawiki_client.MediaWikiClient._api_request",
        side_effect=_mock_api_request,
        autospec=False,
    )


# --- WHENS ---


@when("I upload the file using chunked upload", target_fixture="upload_result")
def upload_file(mediawiki_client, test_file_path, mocker):
    """Upload the file using chunked upload"""
    global _use_default_mock

    # Mock time.sleep to avoid test timeouts
    mocker.patch("time.sleep")

    # Apply default mock if no scenario-specific mock was set
    if _use_default_mock:

        def _mock_api_request(*args, **kwargs):
            params = args[0] if args else kwargs.get("params", {})

            # Handle CSRF token requests
            if params.get("action") == "query" and params.get("meta") == "tokens":
                return {"query": {"tokens": {"csrftoken": "test_token"}}}

            # Upload requests
            return {
                "upload": {
                    "result": "Success",
                    "filekey": "testfilekey.12345.jpg",
                }
            }

        mocker.patch(
            "curator.app.mediawiki_client.MediaWikiClient._api_request",
            side_effect=_mock_api_request,
            autospec=False,
        )

    client = mediawiki_client

    # Try to upload, catch DuplicateUploadError for the duplicate scenario
    try:
        result = client.upload_file(
            filename="test.jpg",
            file_path=test_file_path,
            wikitext="Test wikitext",
            edit_summary="Test upload",
            chunk_size=1024 * 1024,  # 1MB chunks
        )
        exception_raised = None
    except DuplicateUploadError as e:
        result = None
        exception_raised = e

    # Reset flag for next test
    _use_default_mock = True

    return {"result": result, "client": client, "exception": exception_raised}


# --- THENS ---


@then("the upload should succeed")
def upload_succeeds(upload_result):
    assert upload_result["result"].success is True


@then(parsers.parse("all {count:d} chunks should be uploaded"))
def all_chunks_uploaded(upload_result, count):
    # The _api_request should be called: count (chunks) + 1 (commit)
    # CSRF tokens are auto-fetched inside each call
    client = upload_result["client"]
    assert client._api_request.call_count == count + 1


@then("no retries should occur")
def no_retries(upload_result):
    # With 1MB chunk size and 3MB file, we expect 3 chunks + 1 commit = 4 calls
    # CSRF tokens are auto-fetched inside each call
    client = upload_result["client"]
    assert client._api_request.call_count == 4


@then("chunk 2 should be retried once")
def chunk_2_retried(upload_result):
    # chunk1 + chunk2(fail) + chunk2(retry) + chunk3 + commit = 5 calls
    # CSRF tokens are auto-fetched inside each call
    client = upload_result["client"]
    assert client._api_request.call_count == 5


@then("a warning should be logged for the retry")
def warning_logged(upload_result, caplog):
    assert "Chunk 2/3 upload failed" in caplog.text
    assert "retrying in 3 seconds" in caplog.text


@then("the upload should fail")
def upload_fails(upload_result):
    assert upload_result["result"].success is False


@then('the error message should include "Chunk 2/3"')
def error_includes_chunk_num(upload_result):
    assert "Chunk 2/3" in upload_result["result"].error


@then('the error message should include "after 4 attempts"')
def error_includes_attempts(upload_result):
    assert "after 4 attempts" in upload_result["result"].error


@then("chunk 1 should be retried once")
def chunk_1_retried(upload_result):
    # chunk1(fail) + chunk1(retry) + chunk2 + chunk3 + commit = 5 calls
    # CSRF tokens are auto-fetched inside each call
    client = upload_result["client"]
    assert client._api_request.call_count == 5


@then("a DuplicateUploadError should be raised")
def duplicate_error_raised(upload_result):
    assert upload_result["exception"] is not None
    assert isinstance(upload_result["exception"], DuplicateUploadError)


@then("no retries should occur for the duplicate error")
def no_retry_for_duplicate(upload_result):
    # The duplicate check happens AFTER successful API response,
    # so the retry logic should not apply
    client = upload_result["client"]
    # We should see: chunk1 + chunk2 + chunk3 (with duplicate warning)
    # No retry attempts for duplicate errors, and no commit because duplicate is raised
    # With 3 chunks: 3 chunk calls = 3 calls
    # The duplicate is detected after the successful API response for chunk 3
    assert client._api_request.call_count == 3
    assert upload_result["exception"] is not None

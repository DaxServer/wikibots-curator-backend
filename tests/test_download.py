"""Tests for file download functionality."""

import logging
from tempfile import NamedTemporaryFile
from unittest.mock import MagicMock, call

import pytest
import requests.exceptions

from curator.core.config import HTTP_RETRY_DELAYS
from curator.core.errors import SourceCdnError
from curator.mediawiki.commons import download_file

MAX_DOWNLOAD_ATTEMPTS = len(HTTP_RETRY_DELAYS) + 1


def _make_http_error(status_code: int = 504) -> requests.exceptions.HTTPError:
    response = MagicMock()
    response.status_code = status_code
    return requests.exceptions.HTTPError(
        f"Server error '{status_code} Gateway Timeout' for url 'https://example.com/file.jpg'",
        response=response,
    )


def _make_response(mocker, *, http_error=None, content=b"abc"):
    resp = mocker.MagicMock()
    if http_error:
        resp.raise_for_status.side_effect = http_error
    else:
        resp.raise_for_status = mocker.MagicMock()
        resp.headers = {"content-type": "image/jpeg"}
        resp.iter_content = mocker.MagicMock(return_value=[content])
    return resp


def test_download_file_returns_hash(mocker):
    """Test that download_file streams to temp file and returns hash"""
    resp = _make_response(mocker)
    mocker.patch("curator.mediawiki.commons.requests.get", return_value=resp)

    with NamedTemporaryFile() as temp_file:
        data = download_file("http://example.com/file.jpg", temp_file)
        # SHA1 of "abc" is a9993e364706816aba3e25717850c26c9cd0d89d
        assert data == "a9993e364706816aba3e25717850c26c9cd0d89d"


def test_download_file_empty_content(mocker):
    """Test that download_file handles empty content"""
    resp = _make_response(mocker, content=b"")
    mocker.patch("curator.mediawiki.commons.requests.get", return_value=resp)

    with NamedTemporaryFile() as temp_file:
        data = download_file("http://example.com/file.jpg", temp_file)
        # SHA1 of "" is da39a3ee5e6b4b0d3255bfef95601890afd80709
        assert data == "da39a3ee5e6b4b0d3255bfef95601890afd80709"


def test_download_retries_on_http_error_then_succeeds(mocker):
    """504 on first attempt retries and succeeds on second"""
    mock_sleep = mocker.patch("curator.mediawiki.commons.time.sleep")
    error_resp = _make_response(mocker, http_error=_make_http_error(504))
    success_resp = _make_response(mocker, content=b"abc")
    mocker.patch(
        "curator.mediawiki.commons.requests.get",
        side_effect=[error_resp, success_resp],
    )

    with NamedTemporaryFile() as temp_file:
        result = download_file(
            "https://example.com/file.jpg", temp_file, upload_id=1, batch_id=2
        )

    assert result == "a9993e364706816aba3e25717850c26c9cd0d89d"
    mock_sleep.assert_called_once_with(HTTP_RETRY_DELAYS[0])


@pytest.mark.parametrize("status_code", [502, 504])
def test_download_raises_source_cdn_error_after_all_retries_on_5xx(mocker, status_code):
    """5xx (502, 504) on all attempts raises SourceCdnError after retries exhausted"""
    mocker.patch("curator.mediawiki.commons.time.sleep")
    error = _make_http_error(status_code)
    mocker.patch(
        "curator.mediawiki.commons.requests.get",
        side_effect=[
            _make_response(mocker, http_error=error)
            for _ in range(MAX_DOWNLOAD_ATTEMPTS)
        ],
    )

    with NamedTemporaryFile() as temp_file:
        with pytest.raises(SourceCdnError):
            download_file(
                "https://example.com/file.jpg", temp_file, upload_id=1, batch_id=2
            )


def test_download_raises_http_error_after_all_retries_on_4xx(mocker):
    """4xx on all attempts raises HTTPError (not SourceCdnError) — not transient"""
    mocker.patch("curator.mediawiki.commons.time.sleep")
    error = _make_http_error(403)
    mocker.patch(
        "curator.mediawiki.commons.requests.get",
        side_effect=[
            _make_response(mocker, http_error=error)
            for _ in range(MAX_DOWNLOAD_ATTEMPTS)
        ],
    )

    with NamedTemporaryFile() as temp_file:
        with pytest.raises(requests.exceptions.HTTPError):
            download_file(
                "https://example.com/file.jpg", temp_file, upload_id=1, batch_id=2
            )


def test_download_uses_escalating_backoff(mocker):
    """Each retry uses the next delay from HTTP_RETRY_DELAYS"""
    mock_sleep = mocker.patch("curator.mediawiki.commons.time.sleep")
    error = _make_http_error(504)
    success_resp = _make_response(mocker, content=b"abc")
    # Fail 3 times, succeed on 4th
    mocker.patch(
        "curator.mediawiki.commons.requests.get",
        side_effect=[
            _make_response(mocker, http_error=error),
            _make_response(mocker, http_error=error),
            _make_response(mocker, http_error=error),
            success_resp,
        ],
    )

    with NamedTemporaryFile() as temp_file:
        result = download_file(
            "https://example.com/file.jpg", temp_file, upload_id=1, batch_id=2
        )

    assert result == "a9993e364706816aba3e25717850c26c9cd0d89d"
    assert mock_sleep.call_args_list == [
        call(HTTP_RETRY_DELAYS[0]),
        call(HTTP_RETRY_DELAYS[1]),
        call(HTTP_RETRY_DELAYS[2]),
    ]


def test_download_logs_warning_on_http_error_retry(mocker, caplog):
    """A warning is logged when an HTTP error causes a retry"""
    mocker.patch("curator.mediawiki.commons.time.sleep")
    error_resp = _make_response(mocker, http_error=_make_http_error(504))
    success_resp = _make_response(mocker, content=b"abc")
    mocker.patch(
        "curator.mediawiki.commons.requests.get",
        side_effect=[error_resp, success_resp],
    )

    with (
        caplog.at_level(logging.WARNING, logger="curator.mediawiki.commons"),
        NamedTemporaryFile() as temp_file,
    ):
        download_file(
            "https://example.com/file.jpg", temp_file, upload_id=1, batch_id=2
        )

    assert f"attempt 1/{MAX_DOWNLOAD_ATTEMPTS}" in caplog.text
    assert "retrying" in caplog.text


def test_download_logs_error_when_all_retries_exhausted(mocker, caplog):
    """An error is logged when all download retries are exhausted"""
    mocker.patch("curator.mediawiki.commons.time.sleep")
    error = _make_http_error(504)
    mocker.patch(
        "curator.mediawiki.commons.requests.get",
        side_effect=[
            _make_response(mocker, http_error=error)
            for _ in range(MAX_DOWNLOAD_ATTEMPTS)
        ],
    )

    with (
        caplog.at_level(logging.ERROR, logger="curator.mediawiki.commons"),
        NamedTemporaryFile() as temp_file,
    ):
        with pytest.raises(SourceCdnError):
            download_file(
                "https://example.com/file.jpg", temp_file, upload_id=1, batch_id=2
            )

    assert f"{MAX_DOWNLOAD_ATTEMPTS}/{MAX_DOWNLOAD_ATTEMPTS}" in caplog.text
    assert "failed" in caplog.text


def test_download_retries_on_php_content_type(mocker):
    """Retries when server returns application/x-php content type"""
    mock_sleep = mocker.patch("curator.mediawiki.commons.time.sleep")
    php_resp = mocker.MagicMock()
    php_resp.raise_for_status = mocker.MagicMock()
    php_resp.headers = {"content-type": "application/x-php"}

    success_resp = _make_response(mocker, content=b"abc")
    mocker.patch(
        "curator.mediawiki.commons.requests.get",
        side_effect=[php_resp, success_resp],
    )

    with NamedTemporaryFile() as temp_file:
        result = download_file(
            "https://example.com/file.jpg", temp_file, upload_id=1, batch_id=2
        )

    assert result == "a9993e364706816aba3e25717850c26c9cd0d89d"
    mock_sleep.assert_called_once_with(HTTP_RETRY_DELAYS[0])


def test_download_raises_after_all_retries_on_php_content(mocker):
    """Raises ValueError when all retries return application/x-php"""
    mocker.patch("curator.mediawiki.commons.time.sleep")
    php_resps = []
    for _ in range(MAX_DOWNLOAD_ATTEMPTS):
        resp = mocker.MagicMock()
        resp.raise_for_status = mocker.MagicMock()
        resp.headers = {"content-type": "application/x-php"}
        php_resps.append(resp)

    mocker.patch(
        "curator.mediawiki.commons.requests.get",
        side_effect=php_resps,
    )

    with NamedTemporaryFile() as temp_file:
        with pytest.raises(ValueError, match="application/x-php"):
            download_file(
                "https://example.com/file.jpg", temp_file, upload_id=1, batch_id=2
            )


def _iter_then_fail(chunks, error):
    """Yield chunks then raise an error, simulating a partial download"""

    def _iter(*args, **kwargs):
        yield from chunks
        raise error

    return _iter


def test_download_resets_temp_file_on_retry(mocker):
    """Partial download followed by retry produces clean file, not corrupted data"""
    mocker.patch("curator.mediawiki.commons.time.sleep")

    # First response: writes partial data then raises mid-stream
    partial_resp = mocker.MagicMock()
    partial_resp.raise_for_status = mocker.MagicMock()
    partial_resp.headers = {"content-type": "image/jpeg"}
    partial_resp.iter_content = _iter_then_fail(
        [b"partial"], requests.exceptions.ConnectionError("connection reset")
    )

    # Second response: succeeds with full data
    success_resp = _make_response(mocker, content=b"abc")

    mocker.patch(
        "curator.mediawiki.commons.requests.get",
        side_effect=[partial_resp, success_resp],
    )

    with NamedTemporaryFile() as temp_file:
        download_file(
            "https://example.com/file.jpg", temp_file, upload_id=1, batch_id=2
        )

        # File must contain only "abc", not "partialabc"
        temp_file.seek(0)
        assert temp_file.read() == b"abc"


def test_download_closes_response_on_retry(mocker):
    """Response is closed when retrying to avoid connection leaks"""
    mocker.patch("curator.mediawiki.commons.time.sleep")
    error_resp = _make_response(mocker, http_error=_make_http_error(504))
    success_resp = _make_response(mocker, content=b"abc")
    mocker.patch(
        "curator.mediawiki.commons.requests.get",
        side_effect=[error_resp, success_resp],
    )

    with NamedTemporaryFile() as temp_file:
        download_file(
            "https://example.com/file.jpg", temp_file, upload_id=1, batch_id=2
        )

    error_resp.close.assert_called_once()

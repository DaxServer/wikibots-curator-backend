"""Tests for file download functionality."""

import logging
from tempfile import NamedTemporaryFile
from unittest.mock import MagicMock

import httpx
import pytest

from curator.app.commons import download_file


def _make_http_error(status_code: int = 504) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError(
        f"Server error '{status_code} Gateway Timeout' for url 'https://example.com/file.jpg'",
        request=MagicMock(),
        response=MagicMock(),
    )


def _make_stream_ctx(mocker, *, http_error=None, content=b"abc"):
    resp = mocker.MagicMock()
    if http_error:
        resp.raise_for_status.side_effect = http_error
    else:
        resp.raise_for_status = mocker.MagicMock()
        resp.headers = {"content-type": "image/jpeg"}
        resp.iter_bytes = mocker.MagicMock(return_value=[content])
    ctx = mocker.MagicMock()
    ctx.__enter__ = mocker.MagicMock(return_value=resp)
    ctx.__exit__ = mocker.MagicMock(return_value=False)
    return ctx


def test_download_file_returns_bytes(mocker, mock_requests_response):
    """Test that download_file streams to temp file and returns hash"""
    # Mock httpx.stream context manager
    mock_stream = mocker.MagicMock()
    mock_stream.__enter__ = mocker.MagicMock(return_value=mock_requests_response)
    mock_stream.__exit__ = mocker.MagicMock(return_value=False)
    mocker.patch("httpx.stream", return_value=mock_stream)

    # Mock iter_bytes to stream content
    mock_requests_response.iter_bytes = mocker.MagicMock(return_value=[b"abc"])
    mock_requests_response.headers = {"content-type": "image/jpeg"}

    with NamedTemporaryFile() as temp_file:
        data = download_file("http://example.com/file.jpg", temp_file)
        # SHA1 of "abc" is a9993e364706816aba3e25717850c26c9cd0d89d
        assert data == "a9993e364706816aba3e25717850c26c9cd0d89d"


def test_download_file_with_error(mocker, mock_requests_response):
    """Test that download_file handles errors gracefully"""
    # Mock httpx.stream context manager
    mock_stream = mocker.MagicMock()
    mock_stream.__enter__ = mocker.MagicMock(return_value=mock_requests_response)
    mock_stream.__exit__ = mocker.MagicMock(return_value=False)
    mocker.patch("httpx.stream", return_value=mock_stream)

    # Mock iter_bytes to stream empty content
    mock_requests_response.iter_bytes = mocker.MagicMock(return_value=[b""])
    mock_requests_response.headers = {"content-type": "image/jpeg"}

    with NamedTemporaryFile() as temp_file:
        data = download_file("http://example.com/file.jpg", temp_file)
        # SHA1 of "" is da39a3ee5e6b4b0d3255bfef95601890afd80709
        assert data == "da39a3ee5e6b4b0d3255bfef95601890afd80709"


def test_download_retries_on_http_error_then_succeeds(mocker):
    """504 on first attempt retries and succeeds on second"""
    error_ctx = _make_stream_ctx(mocker, http_error=_make_http_error(504))
    success_ctx = _make_stream_ctx(mocker, content=b"abc")
    mocker.patch("httpx.stream", side_effect=[error_ctx, success_ctx])

    with NamedTemporaryFile() as temp_file:
        result = download_file(
            "https://example.com/file.jpg", temp_file, upload_id=1, batch_id=2
        )

    assert result == "a9993e364706816aba3e25717850c26c9cd0d89d"


def test_download_raises_after_all_retries_on_http_error(mocker):
    """504 on all attempts raises after MAX_DOWNLOAD_RETRIES"""
    error = _make_http_error(504)
    mocker.patch(
        "httpx.stream",
        side_effect=[
            _make_stream_ctx(mocker, http_error=error),
            _make_stream_ctx(mocker, http_error=error),
        ],
    )

    with NamedTemporaryFile() as temp_file:
        with pytest.raises(httpx.HTTPStatusError):
            download_file(
                "https://example.com/file.jpg", temp_file, upload_id=1, batch_id=2
            )


def test_download_logs_warning_on_http_error_retry(mocker, caplog):
    """A warning is logged when an HTTP error causes a retry"""
    error_ctx = _make_stream_ctx(mocker, http_error=_make_http_error(504))
    success_ctx = _make_stream_ctx(mocker, content=b"abc")
    mocker.patch("httpx.stream", side_effect=[error_ctx, success_ctx])

    with (
        caplog.at_level(logging.WARNING, logger="curator.app.commons"),
        NamedTemporaryFile() as temp_file,
    ):
        download_file(
            "https://example.com/file.jpg", temp_file, upload_id=1, batch_id=2
        )

    assert "attempt 1/2" in caplog.text
    assert "retrying" in caplog.text


def test_download_logs_error_when_all_retries_exhausted(mocker, caplog):
    """An error is logged when all download retries are exhausted"""
    error = _make_http_error(504)
    mocker.patch(
        "httpx.stream",
        side_effect=[
            _make_stream_ctx(mocker, http_error=error),
            _make_stream_ctx(mocker, http_error=error),
        ],
    )

    with (
        caplog.at_level(logging.ERROR, logger="curator.app.commons"),
        NamedTemporaryFile() as temp_file,
    ):
        with pytest.raises(httpx.HTTPStatusError):
            download_file(
                "https://example.com/file.jpg", temp_file, upload_id=1, batch_id=2
            )

    assert "2/2" in caplog.text
    assert "failed" in caplog.text

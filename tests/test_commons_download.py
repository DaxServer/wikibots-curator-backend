"""Tests for file download functionality."""

from tempfile import NamedTemporaryFile

import pytest

from curator.app.commons import download_file


@pytest.fixture
def mock_mediawiki_client(mocker):
    """Mock MediaWikiClient for tests"""
    from curator.app.mediawiki_client import MediaWikiClient

    mock = mocker.MagicMock(spec=MediaWikiClient)
    return mock


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

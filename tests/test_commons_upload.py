"""Tests for file upload functionality."""

import pytest

from curator.app.commons import (
    DuplicateUploadError,
    ensure_uploaded,
    upload_file_chunked,
)
from curator.app.mediawiki_client import MediaWikiClient, UploadResult
from curator.asyncapi import ErrorLink, Label, Statement
from curator.asyncapi.NoValueSnak import NoValueSnak
from curator.asyncapi.Rank import Rank


@pytest.fixture
def mock_mediawiki_client(mocker):
    """Mock MediaWikiClient for tests"""
    mock = mocker.MagicMock(spec=MediaWikiClient)
    return mock


def test_ensure_uploaded_raises_on_exists_without_upload(mocker, mock_mediawiki_client):
    """Test that ensure_uploaded raises ValueError when file already exists (no upload)"""
    mock_mediawiki_client.file_exists.return_value = True

    with pytest.raises(ValueError, match="already exists"):
        ensure_uploaded(mock_mediawiki_client, False, "x.jpg")

    # Verify file_exists called only ONCE (not twice)
    mock_mediawiki_client.file_exists.assert_called_once_with("x.jpg")


def test_ensure_uploaded_raises_on_missing_after_upload(mocker, mock_mediawiki_client):
    """Test that ensure_uploaded raises ValueError when file missing after upload"""
    mock_mediawiki_client.file_exists.return_value = False

    with pytest.raises(ValueError, match="upload failed"):
        ensure_uploaded(mock_mediawiki_client, True, "x.jpg")

    # Verify file_exists called only ONCE (not twice)
    mock_mediawiki_client.file_exists.assert_called_once_with("x.jpg")


def test_ensure_uploaded_passes_when_successful(mocker, mock_mediawiki_client):
    """Test that ensure_uploaded passes when file exists after upload"""
    mock_mediawiki_client.file_exists.return_value = True

    # Should not raise any exception
    ensure_uploaded(mock_mediawiki_client, True, "x.jpg")

    # Verify file_exists called only ONCE (not twice)
    mock_mediawiki_client.file_exists.assert_called_once_with("x.jpg")


def test_upload_file_chunked_success(mocker, mock_mediawiki_client):
    """Test that upload_file_chunked returns success result when upload succeeds"""
    # Mock the upload to succeed
    mock_mediawiki_client.upload_file.return_value = UploadResult(
        success=True,
        title="File:Test.jpg",
        url="https://commons.wikimedia.org/wiki/File:Test.jpg",
    )
    mock_mediawiki_client.find_duplicates.return_value = []
    mock_mediawiki_client.apply_sdc.return_value = True

    # Mock download_file
    mocker.patch("curator.app.commons.download_file", return_value="abc123")

    # Call upload_file_chunked (without site parameter - new signature)
    result = upload_file_chunked(
        file_name="Test.jpg",
        file_url="http://example.com/test.jpg",
        wikitext="== Summary ==",
        edit_summary="Test upload",
        upload_id=1,
        batch_id=123,
        mediawiki_client=mock_mediawiki_client,
    )

    # Verify result
    assert result["result"] == "success"
    assert result["title"] == "File:Test.jpg"
    assert result["url"] == "https://commons.wikimedia.org/wiki/File:Test.jpg"

    # Verify upload_file was called with correct arguments
    mock_mediawiki_client.upload_file.assert_called_once()
    call_kwargs = mock_mediawiki_client.upload_file.call_args.kwargs
    assert call_kwargs["filename"] == "Test.jpg"
    assert "file_path" in call_kwargs
    assert call_kwargs["wikitext"] == "== Summary =="
    assert call_kwargs["edit_summary"] == "Test upload"


def test_upload_file_chunked_duplicate_raises_error(mocker, mock_mediawiki_client):
    """Test that upload_file_chunked raises DuplicateUploadError when file already exists"""
    # Mock find_duplicates to return list of duplicate files
    # (checked before upload in new implementation)
    mock_mediawiki_client.find_duplicates.return_value = [
        ErrorLink(
            title="File:Existing.jpg",
            url="https://commons.wikimedia.org/wiki/File:Existing.jpg",
        )
    ]

    # Mock download_file
    mocker.patch("curator.app.commons.download_file", return_value="abc123")

    # Call upload_file_chunked and expect DuplicateUploadError
    with pytest.raises(DuplicateUploadError) as exc_info:
        upload_file_chunked(
            file_name="Test.jpg",
            file_url="http://example.com/test.jpg",
            wikitext="== Summary ==",
            edit_summary="Test upload",
            upload_id=1,
            batch_id=123,
            mediawiki_client=mock_mediawiki_client,
        )

    # Verify error message
    assert "already exists" in str(exc_info.value)
    # Verify duplicates are attached to the error
    assert len(exc_info.value.duplicates) == 1
    assert exc_info.value.duplicates[0].title == "File:Existing.jpg"


def test_upload_file_chunked_upload_failure_propagates(mocker, mock_mediawiki_client):
    """Test that upload_file_chunked raises ValueError when upload fails for non-duplicate reasons"""
    # Mock the upload to fail with generic error
    mock_mediawiki_client.upload_file.return_value = UploadResult(
        success=False,
        error="Upload failed: network error",
    )

    # Mock download_file
    mocker.patch("curator.app.commons.download_file", return_value="abc123")

    # Call upload_file_chunked and expect ValueError
    with pytest.raises(ValueError, match="network error"):
        upload_file_chunked(
            file_name="Test.jpg",
            file_url="http://example.com/test.jpg",
            wikitext="== Summary ==",
            edit_summary="Test upload",
            upload_id=1,
            batch_id=123,
            mediawiki_client=mock_mediawiki_client,
        )


def test_upload_file_chunked_applies_sdc(mocker, mock_mediawiki_client):
    """Test that upload_file_chunked applies SDC after successful upload"""
    no_value_snak = NoValueSnak(property="P180")
    statement = Statement(
        mainsnak=no_value_snak,
        rank=Rank.NORMAL,
    )
    sdc = [statement]
    label = Label(language="en", value="Test Label")

    # Mock the upload to succeed
    mock_mediawiki_client.upload_file.return_value = UploadResult(
        success=True,
        title="File:Test.jpg",
        url="https://commons.wikimedia.org/wiki/File:Test.jpg",
    )
    mock_mediawiki_client.apply_sdc.return_value = True

    # Mock download_file
    mocker.patch("curator.app.commons.download_file", return_value="abc123")

    # Call upload_file_chunked with SDC and labels
    result = upload_file_chunked(
        file_name="Test.jpg",
        file_url="http://example.com/test.jpg",
        wikitext="== Summary ==",
        edit_summary="Test upload",
        upload_id=1,
        batch_id=123,
        mediawiki_client=mock_mediawiki_client,
        sdc=sdc,
        labels=label,
    )

    # Verify result
    assert result["result"] == "success"

    # Verify apply_sdc was called with correct parameters
    mock_mediawiki_client.apply_sdc.assert_called_once()
    call_kwargs = mock_mediawiki_client.apply_sdc.call_args.kwargs
    assert call_kwargs["filename"] == "Test.jpg"
    assert call_kwargs["sdc"] is not None
    assert call_kwargs["labels"] is not None
    assert call_kwargs["edit_summary"] == "Test upload"

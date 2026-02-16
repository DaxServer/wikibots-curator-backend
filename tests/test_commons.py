from tempfile import NamedTemporaryFile

import pytest

from curator.app.commons import (
    DuplicateUploadError,
    apply_sdc,
    download_file,
    ensure_uploaded,
    upload_file_chunked,
)
from curator.app.mediawiki_client import MediaWikiClient, UploadResult
from curator.asyncapi import ErrorLink, Label, Statement
from curator.asyncapi.NoValueSnak import NoValueSnak
from curator.asyncapi.Rank import Rank


@pytest.fixture
def mock_mediawiki_client(mocker):
    """Mock MediaWikiClient for apply_sdc tests"""
    mock = mocker.MagicMock(spec=MediaWikiClient)
    mock.apply_sdc.return_value = True
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


def test_apply_sdc_invokes_mediawiki_client(mocker, mock_mediawiki_client):
    """Test that apply_sdc uses MediaWikiClient"""

    no_value_snak = NoValueSnak(property="P180")
    statement = Statement(
        mainsnak=no_value_snak,
        rank=Rank.NORMAL,
    )
    sdc = [statement]

    result = apply_sdc(
        "File:x.jpg",
        sdc=sdc,
        edit_summary="summary",
        labels=None,
        mediawiki_client=mock_mediawiki_client,
    )

    assert result is True
    mock_mediawiki_client.apply_sdc.assert_called_once()
    call_kwargs = mock_mediawiki_client.apply_sdc.call_args.kwargs
    assert call_kwargs["filename"] == "x.jpg"
    assert "sdc" in call_kwargs
    assert call_kwargs["labels"] is None
    assert call_kwargs["edit_summary"] == "summary"
    # Verify SDC was converted to dicts
    assert isinstance(call_kwargs["sdc"], list)
    assert isinstance(call_kwargs["sdc"][0], dict)


def test_apply_sdc_without_labels(mocker, mock_mediawiki_client):
    """Test that apply_sdc works without labels"""

    no_value_snak = NoValueSnak(property="P180")
    statement = Statement(
        mainsnak=no_value_snak,
        rank=Rank.NORMAL,
    )
    sdc = [statement]

    result = apply_sdc(
        "File:x.jpg",
        sdc=sdc,
        edit_summary="summary",
        mediawiki_client=mock_mediawiki_client,
    )

    assert result is True
    mock_mediawiki_client.apply_sdc.assert_called_once()
    call_kwargs = mock_mediawiki_client.apply_sdc.call_args.kwargs
    assert call_kwargs["filename"] == "x.jpg"
    assert call_kwargs["labels"] is None
    assert call_kwargs["edit_summary"] == "summary"


def test_apply_sdc_includes_labels_in_payload_when_provided(
    mocker, mock_mediawiki_client
):
    """Test that apply_sdc includes labels in payload when provided"""

    no_value_snak = NoValueSnak(property="P180")
    statement = Statement(
        mainsnak=no_value_snak,
        rank=Rank.NORMAL,
    )
    sdc = [statement]

    label = Label(language="en", value="Test Label")
    labels = label

    result = apply_sdc(
        "File:x.jpg",
        sdc=sdc,
        edit_summary="summary",
        labels=labels,
        mediawiki_client=mock_mediawiki_client,
    )

    assert result is True
    mock_mediawiki_client.apply_sdc.assert_called_once()
    call_kwargs = mock_mediawiki_client.apply_sdc.call_args.kwargs
    assert call_kwargs["filename"] == "x.jpg"
    assert call_kwargs["labels"] is not None
    assert isinstance(call_kwargs["labels"], list)
    # Labels should be an array matching MediaWiki API format
    assert call_kwargs["labels"][0]["language"] == "en"
    assert call_kwargs["labels"][0]["value"] == "Test Label"


def test_apply_sdc_without_sdc(mocker, mock_mediawiki_client):
    """Test that apply_sdc works without SDC"""

    label = Label(language="en", value="Test Label")
    labels = label

    result = apply_sdc(
        "File:x.jpg",
        edit_summary="summary",
        labels=labels,
        mediawiki_client=mock_mediawiki_client,
    )

    assert result is True
    mock_mediawiki_client.apply_sdc.assert_called_once()
    call_kwargs = mock_mediawiki_client.apply_sdc.call_args.kwargs
    assert call_kwargs["filename"] == "x.jpg"
    assert call_kwargs["sdc"] is None
    assert call_kwargs["labels"] is not None
    assert isinstance(call_kwargs["labels"], list)


def test_apply_sdc_with_empty_data(mocker):
    """Test that apply_sdc works with empty data"""

    mock_mediawiki_client = mocker.MagicMock(spec=MediaWikiClient)
    mock_mediawiki_client.apply_sdc.return_value = False

    result = apply_sdc(
        "File:x.jpg", edit_summary="summary", mediawiki_client=mock_mediawiki_client
    )

    assert result is False
    mock_mediawiki_client.apply_sdc.assert_not_called()


def test_apply_sdc_uses_mediawiki_client_csrf(mocker, mock_mediawiki_client):
    """Test that apply_sdc uses MediaWikiClient.apply_sdc which handles CSRF internally"""

    no_value_snak = NoValueSnak(property="P180")
    statement = Statement(
        mainsnak=no_value_snak,
        rank=Rank.NORMAL,
    )
    sdc = [statement]

    result = apply_sdc(
        file_title="File:test.jpg",
        sdc=sdc,
        edit_summary="summary",
        labels=None,
        mediawiki_client=mock_mediawiki_client,
    )

    # Assert MediaWikiClient.apply_sdc was called (CSRF handled internally)
    assert result is True
    mock_mediawiki_client.apply_sdc.assert_called_once()


def test_apply_sdc_strips_file_prefix_from_title(mocker, mock_mediawiki_client):
    """Test that apply_sdc strips File: prefix from FilePage.title()"""

    no_value_snak = NoValueSnak(property="P180")
    statement = Statement(
        mainsnak=no_value_snak,
        rank=Rank.NORMAL,
    )
    sdc = [statement]

    # Test with title that includes "File:" prefix (from ErrorLink)
    result = apply_sdc(
        "File:Photo from Mapillary 2017-06-24 (168951548443095).jpg",
        sdc=sdc,
        edit_summary="summary",
        labels=None,
        mediawiki_client=mock_mediawiki_client,
    )

    assert result is True
    mock_mediawiki_client.apply_sdc.assert_called_once()
    call_kwargs = mock_mediawiki_client.apply_sdc.call_args.kwargs
    # Verify filename was stripped of "File:" prefix
    assert (
        call_kwargs["filename"]
        == "Photo from Mapillary 2017-06-24 (168951548443095).jpg"
    )


def test_fetch_page_returns_page_data(mocker):
    """Test that _fetch_page returns page data from API"""
    access_token = mocker.MagicMock()
    client = MediaWikiClient(access_token=access_token)

    # Mock API response for existing file (formatversion=2 returns array)
    mock_response = {
        "query": {
            "pages": [
                {
                    "pageid": 12345,
                    "title": "File:Example.jpg",
                    "revisions": [
                        {"slots": {"main": {"content": "Example wikitext content"}}}
                    ],
                }
            ]
        }
    }
    client._api_request = mocker.MagicMock(return_value=mock_response)

    result = client._fetch_page("Example.jpg")

    assert result["pageid"] == 12345
    assert result["title"] == "File:Example.jpg"
    assert (
        result["revisions"][0]["slots"]["main"]["content"] == "Example wikitext content"
    )
    client._api_request.assert_called_once_with(
        {
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "rvlimit": 1,
            "rvslots": "*",
            "titles": "File:Example.jpg",
            "formatversion": "2",
        }
    )


def test_fetch_page_returns_missing_page(mocker):
    """Test that _fetch_page returns page with 'missing' key for non-existent files"""
    access_token = mocker.MagicMock()
    client = MediaWikiClient(access_token=access_token)

    # Mock API response for missing file (formatversion=2 returns array)
    mock_response = {
        "query": {
            "pages": [
                {
                    "title": "File:Nonexistent.jpg",
                    "missing": True,
                }
            ]
        }
    }
    client._api_request = mocker.MagicMock(return_value=mock_response)

    result = client._fetch_page("Nonexistent.jpg")

    assert result["title"] == "File:Nonexistent.jpg"
    assert "missing" in result


def test_file_exists_via_shared_fetch(mocker):
    """Test that file_exists uses _fetch_page and returns bool"""
    access_token = mocker.MagicMock()
    client = MediaWikiClient(access_token=access_token)

    # Test existing file
    client._fetch_page = mocker.MagicMock(
        return_value={
            "pageid": 12345,
            "revisions": [{"slots": {"main": {"content": "content"}}}],
        }
    )
    assert client.file_exists("Example.jpg") is True
    client._fetch_page.assert_called_once_with("Example.jpg")

    # Test missing file
    client._fetch_page.reset_mock()
    client._fetch_page = mocker.MagicMock(
        return_value={"title": "File:Nonexistent.jpg", "missing": True},
    )
    assert client.file_exists("Nonexistent.jpg") is False


def test_null_edit_uses_single_api_call(mocker):
    """Test that null_edit uses shared _fetch_page and makes only ONE API call for edit"""
    access_token = mocker.MagicMock()
    client = MediaWikiClient(access_token=access_token)

    # Mock _fetch_page to return valid page
    client._fetch_page = mocker.MagicMock(
        return_value={
            "pageid": 12345,
            "title": "File:Example.jpg",
            "revisions": [{"slots": {"main": {"content": "Current wikitext"}}}],
        }
    )

    # Mock get_csrf_token and _api_request for edit
    client.get_csrf_token = mocker.MagicMock(return_value="test_token")
    client._api_request = mocker.MagicMock(return_value={"edit": {"result": "Success"}})

    result = client.null_edit("Example.jpg")

    assert result is True
    # Verify _fetch_page was called once
    client._fetch_page.assert_called_once_with("Example.jpg")
    # Verify edit was made with content from fetched page
    client._api_request.assert_called_once()
    call_args = client._api_request.call_args
    assert call_args[0][0]["action"] == "edit"
    assert call_args[1]["data"]["text"] == "Current wikitext"


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

from unittest.mock import patch

import pytest

from curator.app.commons import (
    apply_sdc,
    build_file_page,
    download_file,
    ensure_uploaded,
    perform_upload,
)
from curator.app.mediawiki_client import MediaWikiClient
from curator.asyncapi import Label, Statement
from curator.asyncapi.NoValueSnak import NoValueSnak
from curator.asyncapi.Rank import Rank


@pytest.fixture
def mock_mediawiki_client(mocker):
    """Mock MediaWikiClient for apply_sdc tests"""
    mock = mocker.MagicMock(spec=MediaWikiClient)
    mock.apply_sdc.return_value = True
    return mock


@pytest.fixture
def mock_commons_site(mocker):
    """Mock the create_isolated_site function"""
    return mocker.patch("curator.app.commons.create_isolated_site")


@pytest.fixture
def mock_isolated_site(mocker):
    """Mock the create_isolated_site function"""
    return mocker.patch("curator.app.commons.create_isolated_site")


def test_download_file_returns_bytes(mocker, mock_get, mock_requests_response):
    """Test that download_file returns file bytes"""
    mock_requests_response.content = b"abc"
    mock_get.return_value = mock_requests_response

    data = download_file("http://example.com/file.jpg")
    assert data == b"abc"


def test_download_file_with_error(mocker, mock_get, mock_requests_response):
    """Test that download_file handles errors gracefully"""
    mock_requests_response.content = b""
    mock_get.return_value = mock_requests_response

    data = download_file("http://example.com/file.jpg")
    assert data == b""


def test_build_file_page_uses_named_title(mocker):
    """Test that build_file_page uses named title"""
    with (
        patch("curator.app.commons.Page") as mock_page,
        patch("curator.app.commons.FilePage") as mock_file_page,
    ):
        site = mocker.MagicMock()
        fp = build_file_page(site, "x.jpg")
        mock_page.assert_called_with(site, title="x.jpg", ns=6)
        assert fp is mock_file_page.return_value


def test_perform_upload_passes_args(mocker):
    """Test that perform_upload passes arguments correctly"""
    file_page = mocker.MagicMock()
    perform_upload(file_page, "/tmp/x", "w", "s")
    file_page.upload.assert_called()


def test_ensure_uploaded_raises_on_exists_without_uploaded(mocker):
    """Test that ensure_uploaded raises ValueError when file exists but not uploaded"""
    file_page = mocker.MagicMock()
    file_page.exists.return_value = True
    with pytest.raises(ValueError):
        ensure_uploaded(file_page, False, "x.jpg")


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
    # Labels should be an array matching old pywikibot format
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

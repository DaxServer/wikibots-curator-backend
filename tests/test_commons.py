from unittest.mock import patch

import pytest

from curator.app.commons import (
    apply_sdc,
    build_file_page,
    download_file,
    ensure_uploaded,
    perform_upload,
)
from curator.asyncapi import Label, Statement
from curator.asyncapi.NoValueSnak import NoValueSnak
from curator.asyncapi.Rank import Rank


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


def test_apply_sdc_invokes_simple_request_and_null_edit(mocker):
    """Test that apply_sdc invokes simple_request and null edit"""
    site = mocker.MagicMock()
    req = mocker.MagicMock()
    site.simple_request.return_value = req
    fp = mocker.MagicMock()
    fp.title.return_value = "File:x.jpg"

    no_value_snak = NoValueSnak(property="P180")
    statement = Statement(
        mainsnak=no_value_snak,
        rank=Rank.NORMAL,
    )
    sdc = [statement]

    apply_sdc(site, fp, sdc=sdc, edit_summary="summary", labels=None)
    site.simple_request.assert_called()
    fp.save.assert_called()


def test_apply_sdc_without_labels(mocker):
    """Test that apply_sdc works without labels"""
    site = mocker.MagicMock()
    req = mocker.MagicMock()
    site.simple_request.return_value = req
    site.get_tokens.return_value = {"csrf": "token"}
    fp = mocker.MagicMock()
    fp.title.return_value = "File:x.jpg"

    no_value_snak = NoValueSnak(property="P180")
    statement = Statement(
        mainsnak=no_value_snak,
        rank=Rank.NORMAL,
    )
    sdc = [statement]

    apply_sdc(site, fp, sdc=sdc, edit_summary="summary")

    site.simple_request.assert_called_once_with(
        action="wbeditentity",
        site="commonswiki",
        title="File:x.jpg",
        data='{"claims": [{"mainsnak": {"snaktype": "novalue", "property": "P180"}, "rank": "normal", "qualifiers": {}, "qualifiers-order": [], "references": [], "type": "statement"}]}',
        token="token",
        summary="summary",
        bot=False,
    )


def test_apply_sdc_includes_labels_in_payload_when_provided(mocker):
    """Test that apply_sdc includes labels in payload when provided"""
    site = mocker.MagicMock()
    req = mocker.MagicMock()
    site.simple_request.return_value = req
    site.get_tokens.return_value = {"csrf": "token"}
    fp = mocker.MagicMock()
    fp.title.return_value = "File:x.jpg"

    no_value_snak = NoValueSnak(property="P180")
    statement = Statement(
        mainsnak=no_value_snak,
        rank=Rank.NORMAL,
    )
    sdc = [statement]

    label = Label(language="en", value="Test Label")
    labels = label

    apply_sdc(site, fp, sdc=sdc, edit_summary="summary", labels=labels)

    site.simple_request.assert_called_once_with(
        action="wbeditentity",
        site="commonswiki",
        title="File:x.jpg",
        data='{"claims": [{"mainsnak": {"snaktype": "novalue", "property": "P180"}, "rank": "normal", "qualifiers": {}, "qualifiers-order": [], "references": [], "type": "statement"}], "labels": [{"language": "en", "value": "Test Label"}]}',
        token="token",
        summary="summary",
        bot=False,
    )


def test_apply_sdc_without_sdc(mocker):
    """Test that apply_sdc works without SDC"""
    site = mocker.MagicMock()
    req = mocker.MagicMock()
    site.simple_request.return_value = req
    site.get_tokens.return_value = {"csrf": "token"}
    fp = mocker.MagicMock()
    fp.title.return_value = "File:x.jpg"

    label = Label(language="en", value="Test Label")
    labels = label

    apply_sdc(site, fp, edit_summary="summary", labels=labels)

    site.simple_request.assert_called_once_with(
        action="wbeditentity",
        site="commonswiki",
        title="File:x.jpg",
        data='{"labels": [{"language": "en", "value": "Test Label"}]}',
        token="token",
        summary="summary",
        bot=False,
    )


def test_apply_sdc_with_empty_data(mocker):
    """Test that apply_sdc works with empty data"""
    site = mocker.MagicMock()
    req = mocker.MagicMock()
    site.simple_request.return_value = req
    site.get_tokens.return_value = {"csrf": "token"}
    fp = mocker.MagicMock()
    fp.title.return_value = "File:x.jpg"

    apply_sdc(site, fp, edit_summary="summary")

    # When no SDC data or labels are provided, apply_sdc should return early
    # without calling simple_request
    site.simple_request.assert_not_called()


def test_apply_sdc_with_file_page_object(mocker):
    """Test that apply_sdc works with FilePage object"""
    site = mocker.MagicMock()
    req = mocker.MagicMock()
    site.simple_request.return_value = req
    site.get_tokens.return_value = {"csrf": "token"}

    # Create a mock FilePage
    fp = mocker.MagicMock()
    fp.title.return_value = "File:test.jpg"

    no_value_snak = NoValueSnak(property="P180")
    statement = Statement(
        mainsnak=no_value_snak,
        rank=Rank.NORMAL,
    )
    sdc = [statement]

    apply_sdc(site, fp, sdc=sdc, edit_summary="summary")

    site.simple_request.assert_called_once_with(
        action="wbeditentity",
        site="commonswiki",
        title="File:test.jpg",
        data='{"claims": [{"mainsnak": {"snaktype": "novalue", "property": "P180"}, "rank": "normal", "qualifiers": {}, "qualifiers-order": [], "references": [], "type": "statement"}]}',
        token="token",
        summary="summary",
        bot=False,
    )

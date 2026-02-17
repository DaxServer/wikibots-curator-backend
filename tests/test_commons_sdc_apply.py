"""Tests for applying SDC in commons operations."""

import pytest

from curator.app.commons import apply_sdc
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

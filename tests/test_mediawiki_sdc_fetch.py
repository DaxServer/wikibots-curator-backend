"""Tests for fetching SDC from MediaWiki."""

import pytest
from mwoauth import AccessToken

from curator.app.mediawiki_client import MediaWikiClient


def test_fetch_sdc_returns_statements_and_labels(mocker):
    """Test that fetch_sdc returns statements and labels from API using title"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "entities": {
                "M12345": {
                    "statements": {
                        "P1": [
                            {"mainsnak": {"datatype": "string"}, "type": "statement"}
                        ]
                    },
                    "labels": {"en": {"language": "en", "value": "Test label"}},
                }
            }
        }
    )

    data, labels = mock_client.fetch_sdc("File:Example.jpg")

    assert data is not None
    assert "P1" in data
    assert len(data["P1"]) == 1
    assert data["P1"][0]["type"] == "statement"
    assert labels is not None
    assert "en" in labels
    assert labels["en"]["value"] == "Test label"
    mock_client._api_request.assert_called_once_with(
        {
            "action": "wbgetentities",
            "sites": "commonswiki",
            "titles": "File:Example.jpg",
            "props": "claims|labels",
        }
    )


def test_fetch_sdc_handles_missing_title(mocker):
    """Test that fetch_sdc returns None for missing title"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(return_value={"entities": {}})

    data, labels = mock_client.fetch_sdc("File:Missing.jpg")

    assert data is None
    assert labels is None


def test_fetch_sdc_raises_error_for_nonexistent_file(mocker):
    """Test that fetch_sdc raises exception for non-existent file (entity ID -1)"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "entities": {
                "-1": {
                    "site": "commonswiki",
                    "title": "File:Nonexistent.jpg",
                    "missing": "",
                }
            },
            "success": 1,
        }
    )

    with pytest.raises(ValueError, match="does not exist on Commons"):
        mock_client.fetch_sdc("File:Nonexistent.jpg")


def test_fetch_sdc_handles_missing_statements(mocker):
    """Test that fetch_sdc returns None when statements key is missing"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "entities": {
                "M12345": {"labels": {"en": {"language": "en", "value": "Test"}}}
            }
        }
    )

    data, labels = mock_client.fetch_sdc("File:Example.jpg")

    # When statements is missing/None, data is None but labels may still be returned
    assert data is None
    assert labels is not None


def test_fetch_sdc_handles_file_exists_without_sdc(mocker):
    """Test that fetch_sdc returns None for file that exists but has no SDC created yet"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "entities": {
                "M184245332": {
                    "id": "M184245332",
                    "missing": "",
                }
            },
            "success": 1,
        }
    )

    data, labels = mock_client.fetch_sdc("File:Example.jpg")

    # File exists but SDC not created - return None for both
    assert data is None
    assert labels is None


def test_fetch_sdc_adds_file_prefix_when_missing(mocker):
    """Test that fetch_sdc adds File: prefix when not provided in title"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "entities": {
                "M12345": {
                    "statements": {
                        "P1": [
                            {"mainsnak": {"datatype": "string"}, "type": "statement"}
                        ]
                    },
                    "labels": {"en": {"language": "en", "value": "Test label"}},
                }
            }
        }
    )

    data, labels = mock_client.fetch_sdc("Example.jpg")

    assert data is not None
    assert "P1" in data
    # Verify API was called with File: prefix added
    mock_client._api_request.assert_called_once_with(
        {
            "action": "wbgetentities",
            "sites": "commonswiki",
            "titles": "File:Example.jpg",
            "props": "claims|labels",
        }
    )


def test_fetch_sdc_preserves_file_prefix_when_present(mocker):
    """Test that fetch_sdc preserves File: prefix when already in title"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "entities": {
                "M12345": {
                    "statements": {
                        "P1": [
                            {"mainsnak": {"datatype": "string"}, "type": "statement"}
                        ]
                    },
                    "labels": {"en": {"language": "en", "value": "Test label"}},
                }
            }
        }
    )

    data, labels = mock_client.fetch_sdc("File:Example.jpg")

    assert data is not None
    # Verify API was called with File: prefix preserved
    mock_client._api_request.assert_called_once_with(
        {
            "action": "wbgetentities",
            "sites": "commonswiki",
            "titles": "File:Example.jpg",
            "props": "claims|labels",
        }
    )

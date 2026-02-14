"""Tests for MediaWiki API client"""

import pytest
from mwoauth import AccessToken

from curator.app.mediawiki_client import MediaWikiClient
from curator.asyncapi import ErrorLink


def test_find_duplicates_returns_errorlink_list(mocker):
    """Test that find_duplicates returns list of ErrorLink objects"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "query": {
                "allimages": [
                    {"title": "File:Example1.jpg", "url": "https://example.com/1"},
                    {"title": "File:Example2.jpg", "url": "https://example.com/2"},
                ]
            }
        }
    )

    result = mock_client.find_duplicates("abc123")

    assert len(result) == 2
    assert isinstance(result[0], ErrorLink)
    assert result[0].title == "File:Example1.jpg"
    assert result[0].url == "https://example.com/1"
    assert result[1].title == "File:Example2.jpg"
    assert result[1].url == "https://example.com/2"


def test_find_duplicates_empty_when_no_duplicates(mocker):
    """Test that find_duplicates returns empty list when no duplicates"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={"query": {"allimages": []}}
    )

    result = mock_client.find_duplicates("abc123")

    assert result == []


def test_check_title_blacklisted_returns_false_for_clean_title(mocker):
    """Test that check_title_blacklisted returns (False, '') for clean title"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "titleblacklist": {
                "result": "ok",
            }
        }
    )

    result = mock_client.check_title_blacklisted("Clean_Title.jpg")

    assert result == (False, "")
    mock_client._api_request.assert_called_once_with(
        {
            "action": "titleblacklist",
            "tbaction": "create",
            "tbtitle": "File:Clean_Title.jpg",
        }
    )


def test_check_title_blacklisted_returns_true_for_blacklisted_title(mocker):
    """Test that check_title_blacklisted returns (True, reason) for blacklisted title"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "titleblacklist": {
                "result": "blacklisted",
                "reason": "Promotional content",
            }
        }
    )

    result = mock_client.check_title_blacklisted("Spam_Promo.jpg")

    assert result == (True, "Promotional content")


def test_check_title_blacklisted_returns_false_on_api_error(mocker):
    """Test that check_title_blacklisted returns (False, '') on API error"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(side_effect=Exception("API timeout"))

    result = mock_client.check_title_blacklisted("Error_Title.jpg")

    assert result == (False, "")


def test_check_title_blacklisted_default_reason(mocker):
    """Test that check_title_blacklisted uses default reason when none provided"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "titleblacklist": {
                "result": "blacklisted",
            }
        }
    )

    result = mock_client.check_title_blacklisted("Bad_Title.jpg")

    assert result == (True, "Title is blacklisted")


def test_get_csrf_token_returns_string(mocker):
    """Test that get_csrf_token returns string token"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={"query": {"tokens": {"csrftoken": "test-csrf-token-123\\+\\"}}}
    )

    result = mock_client.get_csrf_token()

    assert isinstance(result, str)
    assert result == "test-csrf-token-123\\+\\"
    mock_client._api_request.assert_called_once_with(
        {"action": "query", "meta": "tokens", "type": "csrf"}
    )


def test_get_csrf_token_handles_api_error(mocker):
    """Test that get_csrf_token raises exception on API error"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(side_effect=Exception("API timeout"))

    with pytest.raises(Exception, match="API timeout"):
        mock_client.get_csrf_token()


def test_fetch_sdc_returns_statements_and_labels(mocker):
    """Test that fetch_sdc returns statements and labels from API"""
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

    data, labels = mock_client.fetch_sdc("M12345")

    assert data is not None
    assert "P1" in data
    assert len(data["P1"]) == 1
    assert data["P1"][0]["type"] == "statement"
    assert labels is not None
    assert "en" in labels
    assert labels["en"]["value"] == "Test label"
    mock_client._api_request.assert_called_once_with(
        {"action": "wbgetentities", "ids": "M12345", "props": "claims|labels"}
    )


def test_fetch_sdc_handles_missing_media_id(mocker):
    """Test that fetch_sdc returns None for missing media ID"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={"entities": {"M99999": {"statements": {}, "labels": {}}}}
    )

    data, labels = mock_client.fetch_sdc("M12345")

    assert data is None
    assert labels is None


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

    data, labels = mock_client.fetch_sdc("M12345")

    # When statements is missing/None, data is None but labels may still be returned
    assert data is None
    assert labels is not None


def test_fetch_sdc_handles_file_exists_without_sdc(mocker):
    """Test that fetch_sdc returns None for file that exists but has no SDC (missing key)"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "entities": {
                "M184008559": {
                    "id": "M184008559",
                    "missing": "",
                }
            },
            "success": 1,
        }
    )

    data, labels = mock_client.fetch_sdc("M184008559")

    # File exists but SDC not created - return None for both
    assert data is None
    assert labels is None


def test_fetch_sdc_raises_error_for_nonexistent_file(mocker):
    """Test that fetch_sdc raises exception for non-existent file (error response)"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "error": {
                "code": "no-such-entity",
                "info": 'Could not find an entity with the ID "M184008559435".',
                "id": "M184008559435",
            }
        }
    )

    with pytest.raises(Exception, match="Could not find an entity"):
        mock_client.fetch_sdc("M184008559435")

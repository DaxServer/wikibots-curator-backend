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

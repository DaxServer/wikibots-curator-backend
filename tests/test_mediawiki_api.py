"""Tests for MediaWiki API request handling"""

import pytest
from mwoauth import AccessToken

from curator.app.mediawiki_client import MediaWikiClient


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

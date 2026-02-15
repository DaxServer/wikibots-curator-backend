"""Tests for MediaWiki API client"""

import json

import pytest
from mwoauth import AccessToken

from curator.app.mediawiki_client import MediaWikiClient
from curator.asyncapi import ErrorLink


def test_find_duplicates_returns_errorlink_list(mocker):
    """Test that find_duplicates returns list of ErrorLink objects with File page URLs"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "batchcomplete": "",
            "query": {
                "allimages": [
                    {
                        "timestamp": "2025-10-04T09:35:35Z",
                        "url": "https://upload.wikimedia.org/wikipedia/commons/6/69/Photo_from_Mapillary_2017-06-24_%28168951548443095%29.jpg",
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Photo_from_Mapillary_2017-06-24_(168951548443095).jpg",
                        "descriptionshorturl": "https://commons.wikimedia.org/w/index.php?curid=176058819",
                        "name": "Photo_from_Mapillary_2017-06-24_(168951548443095).jpg",
                        "ns": 6,
                        "title": "File:Photo from Mapillary 2017-06-24 (168951548443095).jpg",
                    }
                ]
            },
        }
    )

    result = mock_client.find_duplicates("abc123")

    assert len(result) == 1
    assert isinstance(result[0], ErrorLink)
    assert (
        result[0].title == "File:Photo from Mapillary 2017-06-24 (168951548443095).jpg"
    )
    # Should store File page URL, not direct file URL
    assert (
        result[0].url
        == "https://commons.wikimedia.org/wiki/File:Photo_from_Mapillary_2017-06-24_(168951548443095).jpg"
    )


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


def test_apply_sdc_with_sdc_only(mocker):
    """Test that apply_sdc applies SDC statements without labels"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client.get_csrf_token = mocker.MagicMock(return_value="test-token")
    mock_client._api_request = mocker.MagicMock()
    mock_client.null_edit = mocker.MagicMock(return_value=True)

    sdc_data = [{"mainsnak": {"property": "P180"}, "type": "statement"}]

    result = mock_client.apply_sdc(
        "Test.jpg", sdc=sdc_data, labels=None, edit_summary="test"
    )

    assert result is True
    mock_client._api_request.assert_called_once()
    call_kwargs = mock_client._api_request.call_args[1]
    assert call_kwargs["method"] == "POST"
    payload = json.loads(call_kwargs["data"]["data"])
    assert "claims" in payload


def test_apply_sdc_with_labels_only(mocker):
    """Test that apply_sdc applies labels without SDC"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client.get_csrf_token = mocker.MagicMock(return_value="test-token")
    mock_client._api_request = mocker.MagicMock()
    mock_client.null_edit = mocker.MagicMock(return_value=True)

    labels_data = [{"language": "en", "value": "Test Label"}]

    result = mock_client.apply_sdc(
        "Test.jpg", sdc=None, labels=labels_data, edit_summary="test"
    )

    assert result is True
    mock_client._api_request.assert_called_once()
    call_kwargs = mock_client._api_request.call_args[1]
    assert call_kwargs["method"] == "POST"
    payload = json.loads(call_kwargs["data"]["data"])
    assert "labels" in payload
    assert "claims" not in payload


def test_apply_sdc_with_both(mocker):
    """Test that apply sdc applies both SDC and labels"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client.get_csrf_token = mocker.MagicMock(return_value="test-token")
    mock_client._api_request = mocker.MagicMock()
    mock_client.null_edit = mocker.MagicMock(return_value=True)

    sdc_data = [{"mainsnak": {"property": "P180"}, "type": "statement"}]
    labels_data = [{"language": "en", "value": "Test Label"}]

    result = mock_client.apply_sdc(
        "Test.jpg", sdc=sdc_data, labels=labels_data, edit_summary="test"
    )

    assert result is True
    mock_client._api_request.assert_called_once()
    call_kwargs = mock_client._api_request.call_args[1]
    assert call_kwargs["method"] == "POST"
    payload = json.loads(call_kwargs["data"]["data"])
    assert "claims" in payload
    assert "labels" in payload


def test_apply_sdc_with_empty_data(mocker):
    """Test that apply_sdc returns False when no data provided"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client._api_request = mocker.MagicMock()

    result = mock_client.apply_sdc(
        "Test.jpg", sdc=None, labels=None, edit_summary="test"
    )

    assert result is False
    mock_client._api_request.assert_not_called()


def test_apply_sdc_uses_csrf_token(mocker):
    """Test that apply sdc obtains and uses CSRF token"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client.get_csrf_token = mocker.MagicMock(return_value="test-csrf-token")
    mock_client._api_request = mocker.MagicMock()
    mock_client.null_edit = mocker.MagicMock(return_value=True)

    sdc_data = [{"mainsnak": {"property": "P180"}, "type": "statement"}]

    mock_client.apply_sdc("Test.jpg", sdc=sdc_data, labels=None, edit_summary="test")

    mock_client.get_csrf_token.assert_called_once_with()
    call_kwargs = mock_client._api_request.call_args[1]
    assert call_kwargs["data"]["token"] == "test-csrf-token"


def test_null_edit_performs_edit_with_newline(mocker):
    """Test that null_edit fetches page content and performs edit with newline"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client.get_csrf_token = mocker.MagicMock(return_value="test-csrf-token")

    # Mock API responses: first for query, second for edit
    api_responses = [
        # Query response for page content
        {
            "query": {
                "pages": {
                    "12345": {
                        "pageid": 12345,
                        "revisions": [{"*": "Existing wikitext content"}],
                    }
                }
            }
        },
        # Edit response
        {"edit": {"result": "Success"}},
    ]
    mock_client._api_request = mocker.MagicMock(side_effect=api_responses)

    result = mock_client.null_edit("Test_file.jpg")

    assert result is True
    assert mock_client._api_request.call_count == 2

    # First call should fetch page content
    first_call_params = mock_client._api_request.call_args_list[0][0][0]
    assert first_call_params["action"] == "query"
    assert "revisions" in first_call_params["prop"]

    # Second call should perform edit with newline
    second_call_params = mock_client._api_request.call_args_list[1][0][0]
    second_call_data = mock_client._api_request.call_args_list[1][1]["data"]
    assert second_call_params["action"] == "edit"
    assert second_call_data["text"] == "Existing wikitext content\n"
    assert second_call_data["summary"] == "null edit"


def test_null_edit_skips_when_page_not_found(mocker):
    """Test that null_edit returns False when page doesn't exist"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client.get_csrf_token = mocker.MagicMock(return_value="test-csrf-token")

    # Mock query response with missing page
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "query": {"pages": {"-1": {"title": "File:Missing.jpg", "missing": ""}}}
        }
    )

    result = mock_client.null_edit("Missing.jpg")

    assert result is False
    mock_client._api_request.assert_called_once()


def test_apply_sdc_includes_null_edit(mocker):
    """Test that apply_sdc automatically performs null edit after SDC application"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client.get_csrf_token = mocker.MagicMock(return_value="test-csrf-token")
    mock_client.null_edit = mocker.MagicMock(return_value=True)
    mock_client._api_request = mocker.MagicMock()

    sdc_data = [{"mainsnak": {"property": "P180"}, "type": "statement"}]

    result = mock_client.apply_sdc(
        "Test.jpg", sdc=sdc_data, labels=None, edit_summary="test"
    )

    assert result is True
    mock_client.null_edit.assert_called_once_with("Test.jpg")


def test_apply_sdc_skips_null_edit_when_no_data(mocker):
    """Test that apply_sdc returns False and skips null edit when no data provided"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client.null_edit = mocker.MagicMock()

    result = mock_client.apply_sdc(
        "Test.jpg", sdc=None, labels=None, edit_summary="test"
    )

    assert result is False
    mock_client.null_edit.assert_not_called()

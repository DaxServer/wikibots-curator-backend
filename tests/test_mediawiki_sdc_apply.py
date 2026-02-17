"""Tests for applying SDC to MediaWiki."""

import json

from mwoauth import AccessToken

from curator.app.mediawiki_client import MediaWikiClient


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
        # Query response for page content (formatversion=2)
        {
            "query": {
                "pages": [
                    {
                        "pageid": 12345,
                        "revisions": [
                            {
                                "slots": {
                                    "main": {"content": "Existing wikitext content"}
                                }
                            }
                        ],
                    }
                ]
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
    assert second_call_data["text"] == "Existing wikitext content"
    assert second_call_data["summary"] == "null edit"


def test_null_edit_skips_when_page_not_found(mocker):
    """Test that null_edit returns False when page doesn't exist"""
    mock_client = MediaWikiClient(AccessToken("test", "test"))
    mock_client.get_csrf_token = mocker.MagicMock(return_value="test-csrf-token")

    # Mock query response with missing page (formatversion=2)
    mock_client._api_request = mocker.MagicMock(
        return_value={
            "query": {"pages": [{"title": "File:Missing.jpg", "missing": True}]}
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

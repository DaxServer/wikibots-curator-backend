"""Tests for MediaWiki API operations in commons."""

from curator.app.mediawiki_client import MediaWikiClient


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

"""Tests for MediaWiki file operations"""

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

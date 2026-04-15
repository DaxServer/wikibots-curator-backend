"""Tests for WikidataClient"""

from unittest.mock import MagicMock, patch

from mwoauth import AccessToken

from curator.mediawiki.wikidata_client import WikidataClient


def test_fetch_item_returns_entity_dict():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "entities": {"Q123": {"id": "Q123", "claims": {}, "sitelinks": {}}}
    }
    with patch(
        "curator.mediawiki.wikidata_client.requests.Session"
    ) as mock_session_cls:
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_cls.return_value = mock_session
        client = WikidataClient(access_token=AccessToken("v", "s"))
        result = client.fetch_item("Q123")
    assert result["id"] == "Q123"


def test_edit_item_calls_wbeditentity():
    mock_token_response = MagicMock()
    mock_token_response.json.return_value = {"query": {"tokens": {"csrftoken": "tok+"}}}
    mock_edit_response = MagicMock()
    mock_edit_response.json.return_value = {"success": 1}
    with patch(
        "curator.mediawiki.wikidata_client.requests.Session"
    ) as mock_session_cls:
        mock_session = MagicMock()
        mock_session.get.return_value = mock_token_response
        mock_session.post.return_value = mock_edit_response
        mock_session_cls.return_value = mock_session
        client = WikidataClient(access_token=AccessToken("v", "s"))
        client.edit_item("Q123", claims=[{"mainsnak": {}}], sitelinks=None)
        assert mock_session.post.called

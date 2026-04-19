"""Tests for MediaWikiClient recategorization methods."""


def test_get_category_members_returns_file_titles(mediawiki_client, mocker):
    """get_category_members returns list of file titles in category."""
    mediawiki_client._api_request = mocker.MagicMock(
        return_value={
            "query": {
                "categorymembers": [
                    {"title": "File:Photo1.jpg"},
                    {"title": "File:Photo2.jpg"},
                ]
            }
        }
    )

    result = mediawiki_client.get_category_members("Lens focal length 79.0 mm")

    assert result == ["File:Photo1.jpg", "File:Photo2.jpg"]
    mediawiki_client._api_request.assert_called_once_with(
        {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": "Category:Lens focal length 79.0 mm",
            "cmtype": "file",
            "cmlimit": "500",
        }
    )


def test_get_category_members_handles_pagination(mediawiki_client, mocker):
    """get_category_members follows cmcontinue to fetch all pages."""
    mediawiki_client._api_request = mocker.MagicMock(
        side_effect=[
            {
                "query": {"categorymembers": [{"title": "File:A.jpg"}]},
                "continue": {"cmcontinue": "abc|123", "continue": "||"},
            },
            {
                "query": {"categorymembers": [{"title": "File:B.jpg"}]},
            },
        ]
    )

    result = mediawiki_client.get_category_members("Test category")

    assert result == ["File:A.jpg", "File:B.jpg"]
    assert mediawiki_client._api_request.call_count == 2


def test_get_category_members_returns_empty_for_empty_category(
    mediawiki_client, mocker
):
    """get_category_members returns empty list when category has no files."""
    mediawiki_client._api_request = mocker.MagicMock(
        return_value={"query": {"categorymembers": []}}
    )

    result = mediawiki_client.get_category_members("Empty category")

    assert result == []


def test_replace_category_in_page_replaces_and_returns_true(mediawiki_client, mocker):
    """replace_category_in_page edits page replacing source category with target."""
    wikitext = "Some text\n[[Category:Lens focal length 79.0 mm]]\n[[Category:Other]]"
    mediawiki_client._api_request = mocker.MagicMock(
        side_effect=[
            {
                "query": {
                    "pages": {
                        "12345": {
                            "title": "File:Photo.jpg",
                            "revisions": [{"slots": {"main": {"*": wikitext}}}],
                        }
                    }
                }
            },
            {"edit": {"result": "Success", "title": "File:Photo.jpg"}},
        ]
    )

    result = mediawiki_client.replace_category_in_page(
        "File:Photo.jpg",
        "Lens focal length 79.0 mm",
        "Lens focal length 79 mm",
    )

    assert result is True
    edit_call = mediawiki_client._api_request.call_args_list[1]
    posted_text = edit_call[1]["data"]["text"]
    assert "[[Category:Lens focal length 79 mm]]" in posted_text
    assert "[[Category:Lens focal length 79.0 mm]]" not in posted_text
    assert "[[Category:Other]]" in posted_text


def test_replace_category_in_page_preserves_sort_key(mediawiki_client, mocker):
    """replace_category_in_page preserves sort key when replacing category."""
    wikitext = "[[Category:Lens focal length 79.0 mm|sort]]"
    mediawiki_client._api_request = mocker.MagicMock(
        side_effect=[
            {
                "query": {
                    "pages": {
                        "1": {
                            "title": "File:X.jpg",
                            "revisions": [{"slots": {"main": {"*": wikitext}}}],
                        }
                    }
                }
            },
            {"edit": {"result": "Success", "title": "File:X.jpg"}},
        ]
    )

    result = mediawiki_client.replace_category_in_page(
        "File:X.jpg",
        "Lens focal length 79.0 mm",
        "Lens focal length 79 mm",
    )

    assert result is True
    posted_text = mediawiki_client._api_request.call_args_list[1][1]["data"]["text"]
    assert "[[Category:Lens focal length 79 mm|sort]]" in posted_text


def test_replace_category_in_page_returns_false_when_not_found(
    mediawiki_client, mocker
):
    """replace_category_in_page returns False when source category not in page."""
    wikitext = "[[Category:Some other category]]"
    mediawiki_client._api_request = mocker.MagicMock(
        return_value={
            "query": {
                "pages": {
                    "1": {
                        "title": "File:X.jpg",
                        "revisions": [{"slots": {"main": {"*": wikitext}}}],
                    }
                }
            }
        }
    )

    result = mediawiki_client.replace_category_in_page(
        "File:X.jpg",
        "Lens focal length 79.0 mm",
        "Lens focal length 79 mm",
    )

    assert result is False
    assert mediawiki_client._api_request.call_count == 1


def test_replace_category_in_page_normalizes_underscores_in_source(
    mediawiki_client, mocker
):
    """replace_category_in_page matches wikitext spaces when source uses underscores."""
    wikitext = "[[Category:Lens focal length 79,0 mm]]"
    mediawiki_client._api_request = mocker.MagicMock(
        side_effect=[
            {
                "query": {
                    "pages": {
                        "1": {
                            "title": "File:X.jpg",
                            "revisions": [{"slots": {"main": {"*": wikitext}}}],
                        }
                    }
                }
            },
            {"edit": {"result": "Success", "title": "File:X.jpg"}},
        ]
    )

    result = mediawiki_client.replace_category_in_page(
        "File:X.jpg",
        "Lens_focal_length_79,0_mm",
        "Lens focal length 79 mm",
    )

    assert result is True
    posted_text = mediawiki_client._api_request.call_args_list[1][1]["data"]["text"]
    assert "[[Category:Lens focal length 79 mm]]" in posted_text

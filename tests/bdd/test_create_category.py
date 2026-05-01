"""BDD tests for create_category.feature"""

from unittest.mock import MagicMock

from mwoauth import AccessToken
from pytest_bdd import scenario, then, when

from curator.core.handler import Handler

from .conftest_steps import run_sync


@scenario(
    "features/create_category.feature",
    "Successfully creating a category",
)
def test_create_category_success():
    pass


@scenario(
    "features/create_category.feature",
    "Creating a category that already exists returns an error",
)
def test_create_category_already_exists():
    pass


@scenario(
    "features/create_category.feature",
    "Creating a category with a Wikidata QID adds P373 and sitelink",
)
def test_create_category_with_wikidata_qid():
    pass


@scenario(
    "features/create_category.feature",
    "Wikidata edit failure does not prevent category creation success",
)
def test_create_category_wikidata_edit_fails():
    pass


@when('I send a create category request for "Foo" with text "{{subst:unc}}"')
def when_create_category(mock_sender, event_loop, mocker):
    mock_mw = MagicMock()
    mock_mw.create_page.return_value = "Category:Foo"
    mocker.patch("curator.core.handler.MediaWikiClient", return_value=mock_mw)
    h = Handler(
        {
            "username": "testuser",
            "userid": "12345",
            "access_token": AccessToken("v", "s"),
        },
        mock_sender,
        MagicMock(),
    )
    run_sync(h.create_category("Foo", "{{subst:unc}}"), event_loop)


@when('I send a create category request for "Foo" and the page already exists')
def when_create_category_exists(mock_sender, event_loop, mocker):
    mock_mw = MagicMock()
    mock_mw.create_page.side_effect = ValueError("Page already exists")
    mocker.patch(
        "curator.core.handler.MediaWikiClient",
        return_value=mock_mw,
    )
    h = Handler(
        {
            "username": "testuser",
            "userid": "12345",
            "access_token": AccessToken("v", "s"),
        },
        mock_sender,
        MagicMock(),
    )
    run_sync(h.create_category("Foo", "{{subst:unc}}"), event_loop)


@then('I should receive a category created response with title "Category:Foo"')
def then_category_created(mock_sender):
    mock_sender.send_category_created_response.assert_called_once()
    call_args = mock_sender.send_category_created_response.call_args[0][0]
    assert call_args.title == "Category:Foo"


@then("I should receive an error response")
def then_error_received(mock_sender):
    mock_sender.send_error.assert_called_once()


def _make_handler(mock_sender):
    return Handler(
        {
            "username": "testuser",
            "userid": "12345",
            "access_token": AccessToken("v", "s"),
        },
        mock_sender,
        MagicMock(),
    )


def _mock_wikidata_client(mocker):
    mock_wd = MagicMock()
    mock_wd.fetch_item.return_value = {"claims": {}, "sitelinks": {}}
    mocker.patch("curator.core.handler.WikidataClient", return_value=mock_wd)
    return mock_wd


@when(
    'I send a create category request for "Foo" with text "{{WI}}" and wikidata_qid "Q123"',
    target_fixture="mock_wd_client",
)
def when_create_category_with_qid(mock_sender, event_loop, mocker):
    mock_mw = MagicMock()
    mock_mw.create_page.return_value = "Category:Foo"
    mocker.patch("curator.core.handler.MediaWikiClient", return_value=mock_mw)
    mock_wd = _mock_wikidata_client(mocker)
    run_sync(
        _make_handler(mock_sender).create_category("Foo", "{{WI}}", "Q123"), event_loop
    )
    return mock_wd


@when(
    'I send a create category request for "Foo" with text "{{WI}}" and wikidata_qid "Q123" but Wikidata edit fails',
)
def when_create_category_wikidata_fails(mock_sender, event_loop, mocker):
    mock_mw = MagicMock()
    mock_mw.create_page.return_value = "Category:Foo"
    mocker.patch("curator.core.handler.MediaWikiClient", return_value=mock_mw)
    mock_wd = MagicMock()
    mock_wd.fetch_item.return_value = {"claims": {}, "sitelinks": {}}
    mock_wd.edit_item.side_effect = Exception("API error")
    mocker.patch("curator.core.handler.WikidataClient", return_value=mock_wd)
    run_sync(
        _make_handler(mock_sender).create_category("Foo", "{{WI}}", "Q123"), event_loop
    )


@then('the Wikidata item "Q123" should have P373 and sitelink added')
def then_wikidata_edited(mock_wd_client):
    mock_wd_client.edit_item.assert_called_once()
    call_kwargs = mock_wd_client.edit_item.call_args
    assert call_kwargs[0][0] == "Q123"
    assert call_kwargs[0][2] == {
        "commonswiki": {"site": "commonswiki", "title": "Category:Foo"}
    }

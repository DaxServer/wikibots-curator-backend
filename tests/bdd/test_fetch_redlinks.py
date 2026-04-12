"""BDD tests for fetch_redlinks.feature"""

from unittest.mock import MagicMock

from mwoauth import AccessToken
from pytest_bdd import scenario, then, when

from curator.core.handler import Handler

from .conftest_steps import run_sync


@scenario(
    "features/fetch_redlinks.feature",
    "Fetching redlinks returns items from Commons replica",
)
def test_fetch_redlinks():
    pass


@when("I fetch redlinks")
def when_fetch_redlinks(mock_sender, event_loop, mocker):
    mocker.patch(
        "curator.core.handler.get_redlinks",
        return_value=[
            {"title": "Foo_in_Germany", "linked_from": "Category:Foo_in_France"},
            {"title": "Bar_in_Germany", "linked_from": "Category:Bar_in_France"},
        ],
        create=True,
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
    run_sync(h.fetch_redlinks(), event_loop)


@then("I should receive a redlinks response with 2 items")
def then_redlinks_received(mock_sender):
    mock_sender.send_redlinks_response.assert_called_once()
    call_args = mock_sender.send_redlinks_response.call_args[0][0]
    assert len(call_args.items) == 2
    assert call_args.items[0].title == "Foo_in_Germany"
    assert call_args.items[0].linked_from == "Category:Foo_in_France"

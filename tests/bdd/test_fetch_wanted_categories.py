"""BDD tests for fetch_wanted_categories.feature"""

from unittest.mock import MagicMock

from mwoauth import AccessToken
from pytest_bdd import scenario, then, when

from curator.core.handler import Handler

from .conftest_steps import run_sync


@scenario(
    "features/fetch_wanted_categories.feature",
    "Fetching wanted categories returns items from Commons replica",
)
def test_fetch_wanted_categories():
    pass


@when("I fetch wanted categories")
def when_fetch_wanted_categories(mock_sender, event_loop, mocker):
    mocker.patch(
        "curator.core.handler.get_wanted_categories",
        return_value=[
            {
                "title": "Foo_in_Germany",
                "subcats": 1,
                "files": 121,
                "pages": 2,
                "total": 124,
            },
            {
                "title": "Bar_in_Germany",
                "subcats": 0,
                "files": 5,
                "pages": 10,
                "total": 15,
            },
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
    run_sync(h.fetch_wanted_categories(), event_loop)


@then("I should receive a wanted categories response with 2 items")
def then_wanted_categories_received(mock_sender):
    mock_sender.send_wanted_categories_response.assert_called_once()
    call_args = mock_sender.send_wanted_categories_response.call_args[0][0]
    assert len(call_args.items) == 2
    assert call_args.items[0].title == "Foo_in_Germany"
    assert call_args.items[0].subcats == 1
    assert call_args.items[0].files == 121
    assert call_args.items[0].pages == 2
    assert call_args.items[0].total == 124

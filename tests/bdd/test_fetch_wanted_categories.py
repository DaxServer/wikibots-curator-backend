"""BDD tests for fetch_wanted_categories.feature"""

from unittest.mock import MagicMock

from mwoauth import AccessToken
from pytest_bdd import scenario, then, when

from curator.core.handler import Handler

from .conftest_steps import run_sync

_last_query_offset: int | None = None
_last_query_filter: str | None = None


@scenario(
    "features/fetch_wanted_categories.feature",
    "Fetching wanted categories returns items and total from Commons replica",
)
def test_fetch_wanted_categories():
    pass


@scenario(
    "features/fetch_wanted_categories.feature",
    "Fetching wanted categories at an offset passes offset to the query",
)
def test_fetch_wanted_categories_offset():
    pass


def _mock_query(*args, offset: int = 0, filter_text: str | None = None, **kwargs):
    global _last_query_offset, _last_query_filter
    _last_query_offset = offset
    _last_query_filter = filter_text
    return [
        {
            "title": "Foo_in_Germany",
            "subcats": 1,
            "files": 121,
            "pages": 2,
            "total": 124,
        },
        {"title": "Bar_in_Germany", "subcats": 0, "files": 5, "pages": 10, "total": 15},
    ]


@when("I fetch wanted categories at offset 0")
def when_fetch_wanted_categories_offset_0(mock_sender, event_loop, mocker):
    mocker.patch("curator.core.handler.is_ready", return_value=True)
    mocker.patch("curator.core.handler.query", side_effect=_mock_query)
    mocker.patch("curator.core.handler.count", return_value=50)
    h = Handler(
        {
            "username": "testuser",
            "userid": "12345",
            "access_token": AccessToken("v", "s"),
        },
        mock_sender,
        MagicMock(),
    )
    run_sync(h.fetch_wanted_categories(0), event_loop)


@when("I fetch wanted categories at offset 100")
def when_fetch_wanted_categories_offset_100(mock_sender, event_loop, mocker):
    mocker.patch("curator.core.handler.is_ready", return_value=True)
    mocker.patch("curator.core.handler.query", side_effect=_mock_query)
    mocker.patch("curator.core.handler.count", return_value=50)
    h = Handler(
        {
            "username": "testuser",
            "userid": "12345",
            "access_token": AccessToken("v", "s"),
        },
        mock_sender,
        MagicMock(),
    )
    run_sync(h.fetch_wanted_categories(100), event_loop)


@then("I should receive a wanted categories response with 2 items and total 50")
def then_wanted_categories_received(mock_sender):
    mock_sender.send_wanted_categories_response.assert_called_once()
    call_args = mock_sender.send_wanted_categories_response.call_args[0][0]
    assert len(call_args.items) == 2
    assert call_args.total == 50
    assert call_args.items[0].title == "Foo_in_Germany"
    assert call_args.items[0].subcats == 1
    assert call_args.items[0].files == 121
    assert call_args.items[0].pages == 2
    assert call_args.items[0].total == 124


@scenario(
    "features/fetch_wanted_categories.feature",
    "Fetching wanted categories with a filter passes filter text to the query",
)
def test_fetch_wanted_categories_filter():
    pass


@when('I fetch wanted categories with filter "Germany"')
def when_fetch_wanted_categories_filter(mock_sender, event_loop, mocker):
    mocker.patch("curator.core.handler.is_ready", return_value=True)
    mocker.patch("curator.core.handler.query", side_effect=_mock_query)
    mocker.patch("curator.core.handler.count", return_value=2)
    h = Handler(
        {
            "username": "testuser",
            "userid": "12345",
            "access_token": AccessToken("v", "s"),
        },
        mock_sender,
        MagicMock(),
    )
    run_sync(h.fetch_wanted_categories(0, "Germany"), event_loop)


@then('the DuckDB query should have been called with filter "Germany"')
def then_query_called_with_filter():
    assert _last_query_filter == "Germany"


@then("the DuckDB query should have been called with offset 100")
def then_query_called_with_offset():
    assert _last_query_offset == 100

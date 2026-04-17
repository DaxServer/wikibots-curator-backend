"""BDD tests for check_categories_deleted.feature"""

from unittest.mock import MagicMock

from mwoauth import AccessToken
from pytest_bdd import scenario, then, when

from curator.core.handler import Handler

from .conftest_steps import run_sync


@scenario(
    "features/check_categories_deleted.feature",
    "Some categories are deleted, others are not",
)
def test_check_categories_deleted():
    pass


@when('I check if categories "Foo" and "Bar" are deleted and "Foo" is deleted')
def when_check_categories_deleted(mock_sender, event_loop, mocker):
    def _is_deleted(title: str) -> bool:
        return title == "Foo"

    mock_mw = MagicMock()
    mock_mw.is_category_deleted.side_effect = _is_deleted
    mocker.patch(
        "curator.core.handler.MediaWikiClient",
        return_value=mock_mw,
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
    run_sync(h.check_categories_deleted(["Foo", "Bar"]), event_loop)


@then('I should receive a categories deleted response with "Foo" in the deleted list')
def then_categories_deleted_received(mock_sender):
    mock_sender.send_categories_deleted_response.assert_called_once()
    call_args = mock_sender.send_categories_deleted_response.call_args[0][0]
    assert call_args.deleted == ["Foo"]

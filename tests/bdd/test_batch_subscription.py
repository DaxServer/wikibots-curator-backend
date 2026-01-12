"""BDD tests for batch_subscription.feature"""

from unittest.mock import MagicMock

from pytest_bdd import scenario, then, when

from curator.app.handler import Handler

from .conftest import run_sync

# --- Scenarios ---


@scenario("features/batch_subscription.feature", "Subscribing to batch updates")
def test_subscribe_batch():
    pass


@scenario("features/batch_subscription.feature", "Unsubscribing from batch updates")
def test_unsubscribe_batch():
    pass


# --- GIVENS ---


# --- WHENS ---


@when("I subscribe to batch 1")
def when_subscribe_batch(mock_sender, event_loop):
    h = Handler(
        {"username": "testuser", "userid": "12345", "access_token": "v"},
        mock_sender,
        MagicMock(),
    )
    run_sync(h.subscribe_batch(1), event_loop)


@when("I unsubscribe from batch updates")
def when_unsubscribe_batch(mock_sender, event_loop):
    h = Handler(
        {"username": "testuser", "userid": "12345", "access_token": "v"},
        mock_sender,
        MagicMock(),
    )
    run_sync(h.unsubscribe_batch(), event_loop)


# --- THENS ---


@then("I should start receiving real-time updates for that batch")
def then_subscribed(mock_sender):
    mock_sender.send_error.assert_not_called()


@then("I should stop receiving updates for that batch")
def then_unsubscribed(mock_sender):
    mock_sender.send_error.assert_not_called()

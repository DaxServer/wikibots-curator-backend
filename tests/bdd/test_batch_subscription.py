"""BDD tests for batch_subscription.feature"""
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import curator.app.auth as auth_mod
from curator.app.handler import Handler
from curator.app.models import Batch, User
from curator.asyncapi import Creator, Dates, GeoLocation, MediaImage
from pytest_bdd import given, parsers, scenario, then, when

from .conftest import run_sync


# --- Scenarios ---


@scenario("features/batch_subscription.feature", "Subscribing to batch updates")
def test_subscribe_batch():
    pass


@scenario("features/batch_subscription.feature", "Unsubscribing from batch updates")
def test_unsubscribe_batch():
    pass


# --- GIVENS ---


@given(
    parsers.re(r'I am a logged-in user with id "(?P<userid>[^"]+)"'),
    target_fixture="active_user",
)
def step_given_user(userid, mocker, username="testuser"):
    from curator.main import app

    u = {"username": username, "userid": userid, "sub": userid, "access_token": "v"}
    app.dependency_overrides[auth_mod.check_login] = lambda: u
    mocker.patch(
        "starlette.requests.Request.session",
        new_callable=PropertyMock,
        return_value={"user": u},
    )
    return u


@given(parsers.parse('a batch exists with id {batch_id:d} for user "{userid}"'))
def step_given_batch(engine, batch_id, userid):
    from sqlmodel import Session

    with Session(engine) as s:
        s.merge(User(userid=userid, username="testuser"))
        s.add(Batch(id=batch_id, userid=userid))
        s.commit()


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

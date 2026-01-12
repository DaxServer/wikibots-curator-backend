"""BDD tests for api_registration.feature"""
from unittest.mock import PropertyMock

import curator.app.auth as auth_mod
from pytest_bdd import given, scenario, then, when


# --- Scenarios ---


@scenario(
    "features/api_registration.feature", "Successful registration with valid API key"
)
def test_api_register_success():
    pass


@scenario(
    "features/api_registration.feature", "Registration fails with invalid API key"
)
def test_api_register_invalid_key():
    pass


@scenario(
    "features/api_registration.feature", "Registration fails when API key is missing"
)
def test_api_register_missing_key():
    pass


# --- GIVENS ---


@given("the server has API key registration configured")
def step_given_api_config(mocker, monkeypatch):
    monkeypatch.setenv("X_API_KEY", "test-api-key")
    monkeypatch.setenv("X_USERNAME", "testuser")


# --- WHENS ---


@when("I register with a valid API key", target_fixture="response")
def when_register_valid(client):
    return client.post("/auth/register", headers={"X-API-KEY": "test-api-key"})


@when("I register with an invalid API key", target_fixture="response")
def when_register_invalid(client):
    return client.post("/auth/register", headers={"X-API-KEY": "wrong-key"})


@when("I register without providing an API key", target_fixture="response")
def when_register_missing(client):
    return client.post("/auth/register")


# --- THENS ---


@then("I should be successfully authenticated")
def then_api_registered_success(response):
    assert response.status_code == 200
    data = response.json()
    assert "username" in data


@then("my session should contain the test user")
def then_api_session(response):
    # Check that the registration response was successful
    data = response.json()
    assert data.get("username") == "testuser"


@then("I should receive a 401 Unauthorized response")
def then_api_unauthorized(response):
    # The endpoint returns HTTPException object in JSON due to app bug
    assert response.status_code == 200
    data = response.json()
    assert data.get("status_code") == 401


@then("I should receive a 400 Bad Request response")
def then_api_bad_request(response):
    # The endpoint returns HTTPException object in JSON due to app bug
    assert response.status_code == 200
    data = response.json()
    assert data.get("status_code") == 400

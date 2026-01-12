"""BDD tests for authentication.feature"""
from unittest.mock import PropertyMock

import curator.app.auth as auth_mod
from pytest_bdd import given, parsers, scenario, then, when


# --- Scenarios ---


@scenario("features/authentication.feature", "Checking current user identity")
def test_auth_whoami():
    pass


@scenario("features/authentication.feature", "Logging out clears the session")
def test_auth_logout():
    pass


# --- GIVENS ---


@given(
    parsers.re(r'I am a logged-in user with id "(?P<userid>[^"]+)"'),
    target_fixture="active_user",
)
@given(
    parsers.re(
        r'I have an active session for "(?P<username>[^"]+)" with id "(?P<userid>[^"]+)"'
    ),
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


@given(
    parsers.re(r'I am logged in as user "(?P<username>[^"]+)"'),
    target_fixture="active_user",
)
@given(
    parsers.re(r'I have an active session for "(?P<username>[^"]+)"'),
    target_fixture="active_user",
)
def step_given_std_user(username, mocker, session_context):
    from curator.main import app
    from curator.app.auth import check_login
    from curator.admin import check_admin
    from fastapi import HTTPException

    u = {"username": username, "userid": "u1", "sub": "u1", "access_token": "v"}

    app.dependency_overrides[check_login] = lambda: u

    def _f():
        raise HTTPException(403, "Forbidden")

    app.dependency_overrides[check_admin] = _f
    session_dict = {"user": u}
    session_context["dict"] = session_dict
    mocker.patch(
        "starlette.requests.Request.session",
        new_callable=PropertyMock,
        return_value=session_dict,
    )
    return u


# --- WHENS ---


@when('I request "whoami"', target_fixture="response")
def when_whoami(client):
    return client.get("/auth/whoami")


@when("I request to logout", target_fixture="response")
def when_logout(client):
    return client.get("/auth/logout", follow_redirects=False)


# --- THENS ---


@then(
    parsers.re(
        r'the response should contain username "(?P<username>[^"]+)" and id "(?P<userid>[^"]+)"'
    )
)
def then_whoami(response, username, userid):
    assert response.status_code == 200
    data = response.json()
    assert data.get("username") == username
    assert data.get("userid") == userid


@then("I should be redirected to the home page")
def then_logout(response):
    assert response.status_code in [302, 303, 307]


@then("my session should be empty")
def then_empty_sess(session_context):
    # Verify the session dict was cleared by the logout handler
    session_dict = session_context.get("dict")
    assert session_dict is not None, "Session dict not found in context"
    assert "user" not in session_dict, "User key still exists in session"
    assert len(session_dict) == 0, f"Session not empty: {session_dict}"

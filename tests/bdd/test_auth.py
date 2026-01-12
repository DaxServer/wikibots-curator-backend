"""BDD tests for authentication.feature"""

from pytest_bdd import parsers, scenario, then, when

# --- Scenarios ---


@scenario("features/authentication.feature", "Checking current user identity")
def test_auth_whoami():
    pass


@scenario("features/authentication.feature", "Logging out clears the session")
def test_auth_logout():
    pass


# --- GIVENS ---


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

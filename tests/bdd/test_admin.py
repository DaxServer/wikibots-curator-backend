"""BDD tests for admin.feature"""
from unittest.mock import PropertyMock

import curator.app.auth as auth_mod
from curator.admin import check_admin
from curator.app.auth import check_login
from curator.app.models import Batch, User
from pytest_bdd import given, parsers, scenario, then, when


# --- Scenarios ---


@scenario("features/admin.feature", "Admin can list all batches")
def test_admin_list_batches():
    pass


@scenario("features/admin.feature", "Non-admin cannot access admin panel")
def test_admin_no_access():
    pass


@scenario("features/admin.feature", "Admin can list all users")
def test_admin_list_users():
    pass


@scenario(
    "features/admin.feature",
    "Admin users endpoint returns properly serialized user data",
)
def test_admin_users_serialization():
    pass


# --- GIVENS ---


@given(
    parsers.re(r'I am logged in as admin "(?P<username>[^"]+)"'),
    target_fixture="active_user",
)
def step_given_admin(username, mocker):
    from curator.main import app

    u = {
        "username": "DaxServer",
        "userid": "admin123",
        "sub": "admin123",
        "access_token": "v",
    }

    app.dependency_overrides[check_login] = lambda: u
    app.dependency_overrides[check_admin] = lambda: None
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

    u = {"username": username, "userid": "u1", "sub": "u1", "access_token": "v"}

    app.dependency_overrides[check_login] = lambda: u

    def _f():
        from fastapi import HTTPException

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


@given(parsers.parse("there are {count:d} batches in the system"))
def step_given_batches(engine, count):
    from sqlmodel import Session

    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))
        for i in range(count):
            s.add(Batch(userid="12345"))
        s.commit()


@given(parsers.parse("there are {count:d} users in the system"))
def step_given_users(engine, count):
    from sqlmodel import Session

    with Session(engine) as s:
        for i in range(count):
            s.add(User(userid=f"u{i}", username=f"user{i}"))
        s.commit()


# --- WHENS ---


@when("I request the admin list of batches", target_fixture="response")
def when_adm_batches(client):
    return client.get("/api/admin/batches")


@when("I request the admin list of users", target_fixture="response")
def when_adm_users(client):
    return client.get("/api/admin/users")


# --- THENS ---


@then(parsers.parse("the response should contain {count:d} batches"))
def then_admin_batches(response, count):
    assert response.status_code == 200
    assert len(response.json()["items"]) == count


@then(parsers.parse("the response should contain {count:d} users"))
def then_admin_users(response, count):
    assert response.status_code == 200
    assert response.json()["total"] == count


@then("each user should have username and userid fields")
def then_admin_users_serialized(response):
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    items = data["items"]
    assert len(items) > 0
    for user in items:
        assert "username" in user, f"User missing username field: {user}"
        assert "userid" in user, f"User missing userid field: {user}"
        assert isinstance(user["username"], str), f"username should be string: {user}"
        assert isinstance(user["userid"], str), f"userid should be string: {user}"


@then("I should receive a 403 Forbidden response")
def then_forbidden(response):
    assert response.status_code == 403

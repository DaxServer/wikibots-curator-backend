"""BDD tests for admin.feature"""
from curator.app.models import Batch
from curator.app.models import User
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

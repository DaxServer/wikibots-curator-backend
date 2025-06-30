import pytest
from fastapi.testclient import TestClient
from curator.main import app
from pathlib import Path
import os

# Ensure a consistent secret key for predictable session encoding during tests
TEST_SECRET_KEY = "testsecretkey"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "dummy_test_token_for_app_init")

    def mock_setup_frontend_assets_replacement():
        project_root = Path(__file__).resolve().parent.parent
        frontend_dir_for_tests = project_root / "frontend"
        dist_dir = frontend_dir_for_tests / "dist"
        assets_dir = dist_dir / "assets"

        os.makedirs(assets_dir, exist_ok=True)
        with open(dist_dir / "index.html", "w") as f:
            f.write("<html><head><title>Mock Index</title></head><body>Mock Content</body></html>")

    monkeypatch.setattr("curator.main.setup_frontend_assets", mock_setup_frontend_assets_replacement)

    with TestClient(app) as c:
        yield c


def test_successful_registration_and_whoami(client, monkeypatch):
    """Test successful API key registration and session verification via /whoami."""
    monkeypatch.setenv("X_API_KEY", "test_api_key_123")
    monkeypatch.setenv("X_USERNAME", "test_user")
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    response = client.post("/auth/register", json={"api_key": "test_api_key_123"})
    assert response.status_code == 200
    assert response.json() == {"message": "User registered successfully", "username": "test_user"}

    whoami_response = client.get("/auth/whoami")
    assert whoami_response.status_code == 200
    assert whoami_response.json() == {"username": "test_user", "authorized": True}


def test_invalid_api_key(client, monkeypatch):
    """Test registration attempt with an invalid API key."""
    monkeypatch.setenv("X_API_KEY", "correct_key")
    monkeypatch.setenv("X_USERNAME", "test_user_invalid_key")
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    response = client.post("/auth/register", json={"api_key": "wrong_key"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}

    whoami_response = client.get("/auth/whoami")
    assert whoami_response.status_code == 401
    assert whoami_response.json() == {"message": "Not authenticated"}


def test_missing_api_key_in_request_body(client, monkeypatch):
    """Test registration attempt with missing api_key in the request body."""
    monkeypatch.setenv("X_API_KEY", "any_key")
    monkeypatch.setenv("X_USERNAME", "any_user")
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    response = client.post("/auth/register", json={})
    assert response.status_code == 422  # Unprocessable Entity for Pydantic validation error

    response_missing_field = client.post("/auth/register", json={"other_field": "value"})
    assert response_missing_field.status_code == 422


def test_missing_x_api_key_env_variable(client, monkeypatch):
    """Test registration when X_API_KEY environment variable is not set."""
    monkeypatch.setenv("X_USERNAME", "user_no_api_key_env")
    monkeypatch.delenv("X_API_KEY", raising=False)
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    response = client.post("/auth/register", json={"api_key": "any_key_ L8"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Server configuration error: API key or username not set"}


def test_missing_x_username_env_variable(client, monkeypatch):
    """Test registration when X_USERNAME environment variable is not set."""
    monkeypatch.setenv("X_API_KEY", "key_no_username_env")
    monkeypatch.delenv("X_USERNAME", raising=False)
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    response = client.post("/auth/register", json={"api_key": "key_no_username_env"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Server configuration error: API key or username not set"}


def test_whoami_not_authenticated(client, monkeypatch):
    """Test /whoami when no user is authenticated."""
    monkeypatch.setenv("X_USERNAME", "some_admin_user")
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    response = client.get("/auth/whoami")
    assert response.status_code == 401
    assert response.json() == {"message": "Not authenticated"}

def test_successful_registration_then_logout_then_whoami(client, monkeypatch):
    """Test successful registration, then logout, then check /whoami."""
    monkeypatch.setenv("X_API_KEY", "test_api_key_logout")
    monkeypatch.setenv("X_USERNAME", "test_user_logout")
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    reg_response = client.post("/auth/register", json={"api_key": "test_api_key_logout"})
    assert reg_response.status_code == 200
    assert reg_response.json()["username"] == "test_user_logout"

    whoami_auth_response = client.get("/auth/whoami")
    assert whoami_auth_response.status_code == 200
    assert whoami_auth_response.json()["username"] == "test_user_logout"

    logout_response = client.get("/auth/logout")
    assert logout_response.status_code == 200
    assert logout_response.url == "http://testserver/"


    whoami_not_auth_response = client.get("/auth/whoami")
    assert whoami_not_auth_response.status_code == 401
    assert whoami_not_auth_response.json() == {"message": "Not authenticated"}


def test_session_cookie_set_after_registration(client, monkeypatch):
    monkeypatch.setenv("X_API_KEY", "cookie_test_key")
    monkeypatch.setenv("X_USERNAME", "cookie_test_user")
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    response = client.post("/auth/register", json={"api_key": "cookie_test_key"})
    assert response.status_code == 200
    assert "session" in response.cookies

def test_session_cookie_cleared_after_logout(client, monkeypatch):
    monkeypatch.setenv("X_API_KEY", "logout_cookie_key")
    monkeypatch.setenv("X_USERNAME", "logout_cookie_user")
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    client.post("/auth/register", json={"api_key": "logout_cookie_key"})
    assert "session" in client.cookies

    response = client.get("/auth/logout", follow_redirects=False)
    assert response.status_code == 307
    # Cookies being cleared (e.g., with Max-Age=0) might not appear in response.cookies.
    # The critical check is that the client's cookie jar is updated and subsequent requests are unauthenticated.

    whoami_response = client.get("/auth/whoami")
    assert whoami_response.status_code == 401
    assert "session" not in client.cookies or client.cookies.get("session") == "" or client.cookies.get("session") == "null"


def test_root_path_exists(client):
    """Test the root path '/' serves the mocked index.html."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")

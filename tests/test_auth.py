import pytest
from fastapi.testclient import TestClient
from curator.main import app

# Ensure a consistent secret key for predictable session encoding during tests
TEST_SECRET_KEY = "testsecretkey"

# Apply the test secret key to the app's session middleware
for middleware in app.user_middleware:
    if middleware.cls.__name__ == "SessionMiddleware":
        middleware.options["secret_key"] = TEST_SECRET_KEY
        break


@pytest.fixture
def client():
    # Re-initialize client for each test to ensure clean sessions
    # and application state.
    # Apply the test secret key to the app's session middleware
    # This is important if the app instance is recreated or modified elsewhere
    # or to ensure it's set before TestClient initializes.
    original_secret_key = None
    for i, mw in enumerate(app.user_middleware):
        if mw.cls.__name__ == "SessionMiddleware":
            original_secret_key = mw.options.get("secret_key")
            app.user_middleware[i].options["secret_key"] = TEST_SECRET_KEY
            break

    with TestClient(app) as c:
        yield c

    # Restore original secret key if it was changed
    if original_secret_key is not None:
        for i, mw in enumerate(app.user_middleware):
            if mw.cls.__name__ == "SessionMiddleware":
                app.user_middleware[i].options["secret_key"] = original_secret_key
                break


def test_successful_registration_and_whoami(client, monkeypatch):
    """Test successful API key registration and session verification via /whoami."""
    monkeypatch.setenv("X_API_KEY", "test_api_key_123")
    monkeypatch.setenv("X_USERNAME", "test_user")
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY) # Ensure middleware uses this

    response = client.post("/auth/register", json={"api_key": "test_api_key_123"})
    assert response.status_code == 200
    assert response.json() == {"message": "User registered successfully", "username": "test_user"}

    # Verify session with /whoami
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

    # Verify no session was created
    whoami_response = client.get("/auth/whoami")
    assert whoami_response.status_code == 401
    assert whoami_response.json() == {"message": "Not authenticated"}


def test_missing_api_key_in_request_body(client, monkeypatch):
    """Test registration attempt with missing api_key in the request body."""
    monkeypatch.setenv("X_API_KEY", "any_key")
    monkeypatch.setenv("X_USERNAME", "any_user")
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    response = client.post("/auth/register", json={})  # Empty JSON
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
    # Ensure no relevant env vars are accidentally inherited if not monkeypatched
    monkeypatch.setenv("X_USERNAME", "some_admin_user") # whoami compares against this
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    response = client.get("/auth/whoami")
    assert response.status_code == 401
    assert response.json() == {"message": "Not authenticated"}

def test_successful_registration_then_logout_then_whoami(client, monkeypatch):
    """Test successful registration, then logout, then check /whoami."""
    monkeypatch.setenv("X_API_KEY", "test_api_key_logout")
    monkeypatch.setenv("X_USERNAME", "test_user_logout")
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    # Register
    reg_response = client.post("/auth/register", json={"api_key": "test_api_key_logout"})
    assert reg_response.status_code == 200
    assert reg_response.json()["username"] == "test_user_logout"

    # Check whoami - should be authenticated
    whoami_auth_response = client.get("/auth/whoami")
    assert whoami_auth_response.status_code == 200
    assert whoami_auth_response.json()["username"] == "test_user_logout"

    # Logout
    logout_response = client.get("/auth/logout")
    assert logout_response.status_code == 200 # Redirects to '/', client follows
    # Ensure the client is now at '/'
    assert logout_response.url == "http://testserver/"


    # Check whoami again - should NOT be authenticated
    whoami_not_auth_response = client.get("/auth/whoami")
    assert whoami_not_auth_response.status_code == 401
    assert whoami_not_auth_response.json() == {"message": "Not authenticated"}

# It's good practice to also ensure that the SECRET_KEY environment variable
# is being used by SessionMiddleware. If it's not set, SessionMiddleware
# might create a random one, making session tests unpredictable.
# The client fixture now attempts to set a consistent TEST_SECRET_KEY.
# Additionally, tests monkeypatch SECRET_KEY to ensure the app uses it.

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

    # Register to establish session
    client.post("/auth/register", json={"api_key": "logout_cookie_key"})
    assert "session" in client.cookies # Ensure session cookie was set

    # Logout
    response = client.get("/auth/logout", allow_redirects=False) # Don't follow redirect to check cookie on this response
    assert response.status_code == 307 # Should be a redirect
    # The session cookie should be cleared. The `TestClient` updates its own cookie jar.
    # A common way to clear a cookie is to set its value to empty and max-age to 0.
    # Starlette's SessionMiddleware sets the cookie value to "null" and max-age to 0.
    assert "session" in response.cookies
    # The exact value might vary or how TestClient presents it.
    # A more robust check is that subsequent requests are unauthenticated.

    # Check that the client's cookie jar has effectively cleared the session
    # This can be tricky as TestClient might not expose the raw Set-Cookie header's Max-Age.
    # The most reliable check is behavior:
    whoami_response = client.get("/auth/whoami")
    assert whoami_response.status_code == 401
    assert "session" not in client.cookies or client.cookies.get("session") == "" or client.cookies.get("session") == "null"


# Add a test for the root path to ensure it's available,
# as logout redirects there and some tests check the redirect URL.
def test_root_path_exists(client):
    # This test depends on the lifespan event setting up frontend assets.
    # If 'dist/index.html' doesn't exist where expected, this will fail.
    # For now, let's assume it's correctly mocked or handled by the app setup.
    # In a real CI environment, frontend assets would need to be built or mocked.
    # We can't easily mock the FileResponse target file here without more complex setup.
    # So, we'll rely on the app's setup to handle this.
    # If the file doesn't exist, main.py's lifespan would sys.exit(1)
    # which TestClient might not handle gracefully or might translate to a 500.

    # Temporarily skip if frontend assets are not available, as per main.py logic
    frontend_dist_index = os.path.join(app.state.frontend_dir, 'dist/index.html')
    if not os.path.exists(frontend_dist_index):
        pytest.skip("Frontend dist/index.html not found, skipping root path test")

    response = client.get("/")
    assert response.status_code == 200 # Expect HTML content
    assert response.headers["content-type"].startswith("text/html")

# Need to import os for the skip condition in test_root_path_exists
import os

# Need to ensure app.state.frontend_dir is set if used in skip condition
# This should be set by setup_frontend_assets() in the lifespan.
# If TestClient(app) itself triggers the lifespan, it should be available.
# Let's ensure frontend_dir is accessible for the skip logic.
# This would typically be handled by the app's startup logic.
# If app.state is not populated, we might need to call the lifespan events manually
# or ensure TestClient does it.
# For now, assuming TestClient(app) correctly runs the lifespan.
# The frontend_dir is derived from `Path(__file__).parent.parent.parent / "frontend"`
# in frontend_utils.py. This path needs to be correct relative to test execution.

# Final check on SessionMiddleware setup in client fixture:
# It's crucial that `app.add_middleware(SessionMiddleware, secret_key=...)` in `main.py`
# either uses a fixed key for tests or that the fixture correctly overrides it *before*
# `TestClient(app)` is called if the client instantiation itself finalizes middleware.
# The current fixture modifies `app.user_middleware` which is generally correct.
# The `monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)` in tests ensures that if
# `os.environ.get('SECRET_KEY')` is used by the middleware at instantiation time,
# it gets the test key.
# The initial block setting `TEST_SECRET_KEY` directly on `app.user_middleware`
# is a good safeguard.

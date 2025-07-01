import os
from unittest.mock import patch, AsyncMock

from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
import pytest

from curator.main import app
from curator.toolforge import verify_user, JobConfig

# Set X_USERNAME for tests
os.environ["X_USERNAME"] = "testuser"

client = TestClient(app)


@pytest.fixture
def mock_verify_user_valid():
    mock = AsyncMock(return_value="testuser")
    return mock


@pytest.fixture
def mock_verify_user_invalid():  # This fixture will be used by tests that expect a 401
    async def raiser_401(request: Request):  # Correct signature for a dependency
        raise HTTPException(status_code=401, detail="Unauthorized")

    return raiser_401


@patch("curator.toolforge.make_toolforge_request")
def test_get_tool_jobs(mock_make_request):
    """Test the endpoint to get jobs for a specific tool."""
    mock_response = {"jobs": [{"id": "job1", "status": "running"}]}
    mock_make_request.return_value = mock_response

    response = client.get("/api/toolforge/jobs/v1/tool/test-tool/jobs/")
    assert response.status_code == 200
    assert response.json() == mock_response
    mock_make_request.assert_called_once_with(
        "get",
        "https://api.svc.tools.eqiad1.wikimedia.cloud:30003/jobs/v1/tool/test-tool/jobs/",
    )


@patch("curator.toolforge.make_toolforge_request")
def test_post_tool_job(mock_make_request, mock_verify_user_valid):
    """Test the endpoint to create a new job for a specific tool."""
    app.dependency_overrides[verify_user] = lambda: mock_verify_user_valid
    mock_response = {"id": "job1", "status": "pending"}
    mock_make_request.return_value = mock_response

    job_config_data = {
        "name": "test-job",
        "cmd": "echo 'Hello, World!'",
        "imagename": "debian:latest",
    }
    job_config_obj = JobConfig(**job_config_data)

    response = client.post(
        "/api/toolforge/jobs/v1/tool/test-tool/jobs/",
        json=job_config_data,
    )

    assert response.status_code == 200
    assert response.json() == mock_response
    mock_make_request.assert_called_once_with(
        "post",
        "https://api.svc.tools.eqiad1.wikimedia.cloud:30003/jobs/v1/tool/test-tool/jobs/",
        job_config_obj.model_dump(exclude_unset=True),
    )
    app.dependency_overrides = {}


@patch("curator.toolforge.make_toolforge_request")
def test_delete_tool_job(mock_make_request, mock_verify_user_valid):
    """Test the endpoint to delete a job by its ID."""
    app.dependency_overrides[verify_user] = lambda: mock_verify_user_valid
    mock_response = {"status": "deleted"}
    mock_make_request.return_value = mock_response

    response = client.delete(
        "/api/toolforge/jobs/v1/tool/test-tool/jobs/job1",
    )

    assert response.status_code == 200
    assert response.json() == mock_response
    mock_make_request.assert_called_once_with(
        "delete",
        "https://api.svc.tools.eqiad1.wikimedia.cloud:30003/jobs/v1/tool/test-tool/jobs/job1",
    )
    app.dependency_overrides = {}


def test_post_tool_job_unauthorized(mock_verify_user_invalid):
    """Test POST endpoint returns 401 when user is not authorized."""
    app.dependency_overrides[verify_user] = mock_verify_user_invalid

    job_config = {
        "name": "test-job",
        "cmd": "echo 'Hello, World!'",
        "imagename": "debian:latest",
    }
    response = client.post(
        "/api/toolforge/jobs/v1/tool/test-tool/jobs/", json=job_config
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"
    app.dependency_overrides = {}


def test_delete_tool_job_unauthorized(mock_verify_user_invalid):
    """Test DELETE endpoint returns 401 when user is not authorized."""
    app.dependency_overrides[verify_user] = mock_verify_user_invalid

    response = client.delete("/api/toolforge/jobs/v1/tool/test-tool/jobs/job1")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"
    app.dependency_overrides = {}


@patch("curator.toolforge.make_toolforge_request")  # Patch to prevent actual HTTP call
def test_post_tool_job_missing_x_username(mock_make_request, monkeypatch):
    """Test POST endpoint returns 401 when X_USERNAME is not set on the server, using actual verify_user logic."""
    # Store original X_USERNAME from module to restore later if necessary, though monkeypatch handles os.environ
    import curator.toolforge

    original_module_x_username = getattr(
        curator.toolforge, "X_USERNAME", "AttributeNotSet"
    )

    monkeypatch.delenv("X_USERNAME", raising=False)

    # Reload the module to ensure it picks up the absence of X_USERNAME from os.environ
    from importlib import reload

    reload(curator.toolforge)
    # Directly ensure X_USERNAME in the reloaded module is None
    monkeypatch.setattr(curator.toolforge, "X_USERNAME", None)

    # IMPORTANT: No dependency_override for verify_user here.
    # We want the actual verify_user to run with X_USERNAME being None.
    # The client will have no session data for 'user' by default.
    # So verify_user will see request.session.get('user') as None,
    # causing the `if user_session_data and user_session_data.get('username') == X_USERNAME:`
    # check to fail (None and ... is False), leading to HTTP 401.

    job_config = {
        "name": "test-job",
        "cmd": "echo 'Hello, World!'",
        "imagename": "debian:latest",
    }
    response = client.post(
        "/api/toolforge/jobs/v1/tool/test-tool/jobs/", json=job_config
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"

    # Clean up: reload the module again to restore its original X_USERNAME state
    # if it was based on an environment variable that monkeypatch will restore.
    # If original_module_x_username was 'AttributeNotSet' or None, this might not be strictly needed
    # but good for hygiene if other tests depend on the initial state of X_USERNAME.
    # monkeypatch automatically undoes its changes to os.environ and module attributes
    # after the test, so direct restoration might not be needed if module is re-imported/reloaded
    # by other tests or test setup. For safety, we ensure a clean state for subsequent reloads.
    if original_module_x_username != "AttributeNotSet":
        monkeypatch.setattr(curator.toolforge, "X_USERNAME", original_module_x_username)
    # No need to manually restore os.environ["X_USERNAME"], monkeypatch handles it.
    # No need to clear app.dependency_overrides as none was set for this test.

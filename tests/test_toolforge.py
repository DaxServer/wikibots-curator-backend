import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from curator.main import app

# Set up test API key
os.environ["X_API_KEY"] = "test-api-key"

client = TestClient(app)


@patch("curator.toolforge.get_jobs")
def test_get_tool_jobs(mock_get_jobs):
    """Test the endpoint to get jobs for a specific tool."""
    # Mock the response from get_jobs
    mock_response = {"jobs": [{"id": "job1", "status": "running"}]}
    mock_get_jobs.return_value = mock_response

    # Test the endpoint
    response = client.get("/api/toolforge/jobs/v1/tool/test-tool/jobs/", headers={"X-API-KEY": "test-api-key"})

    # Verify the response
    assert response.status_code == 200
    assert response.json() == mock_response

    # Verify that get_jobs was called with the correct tool name
    mock_get_jobs.assert_called_once_with("test-tool")


@patch("curator.toolforge.post_job")
def test_post_tool_job(mock_post_job):
    """Test the endpoint to create a new job for a specific tool."""
    # Mock the response from post_job
    mock_response = {"id": "job1", "status": "pending"}
    mock_post_job.return_value = mock_response

    # Test job configuration
    job_config = {
        "name": "test-job",
        "cmd": "echo 'Hello, World!'",
        "imagename": "debian:latest"
    }

    # Test the endpoint
    response = client.post(
        "/api/toolforge/jobs/v1/tool/test-tool/jobs/",
        json=job_config,
        headers={"X-API-KEY": "test-api-key"}
    )

    # Verify the response
    assert response.status_code == 200
    assert response.json() == mock_response

    # Verify that post_job was called once
    mock_post_job.assert_called_once()

    # Verify that post_job was called with the correct tool name
    args, _ = mock_post_job.call_args
    assert args[0] == "test-tool"

    # Verify that post_job was called with a JobConfig object with the correct values
    job_config_obj = args[1]
    assert job_config_obj.name == job_config["name"]
    assert job_config_obj.cmd == job_config["cmd"]
    assert job_config_obj.imagename == job_config["imagename"]


@patch("curator.toolforge.delete_job")
def test_delete_tool_job(mock_delete_job):
    """Test the endpoint to delete a job by its ID."""
    # Mock the response from delete_job
    mock_response = {"status": "deleted"}
    mock_delete_job.return_value = mock_response

    # Test the endpoint
    response = client.delete(
        "/api/toolforge/jobs/v1/tool/test-tool/jobs/job1",
        headers={"X-API-KEY": "test-api-key"}
    )

    # Verify the response
    assert response.status_code == 200
    assert response.json() == mock_response

    # Verify that delete_job was called with the correct arguments
    mock_delete_job.assert_called_once_with("test-tool", "job1")


def test_missing_api_key():
    """Test that endpoints requiring authentication return 403 when API key is missing."""
    # Test GET endpoint without API key
    response = client.get("/api/toolforge/jobs/v1/tool/test-tool/jobs/")
    assert response.status_code == 403

    # Test POST endpoint without API key
    job_config = {"name": "test-job", "cmd": "echo 'Hello, World!'", "imagename": "debian:latest"}
    response = client.post("/api/toolforge/jobs/v1/tool/test-tool/jobs/", json=job_config)
    assert response.status_code == 403

    # Test DELETE endpoint without API key
    response = client.delete("/api/toolforge/jobs/v1/tool/test-tool/jobs/job1")
    assert response.status_code == 403


def test_invalid_api_key():
    """Test that endpoints requiring authentication return 401 when API key is invalid."""
    # Test GET endpoint with invalid API key
    response = client.get("/api/toolforge/jobs/v1/tool/test-tool/jobs/", headers={"X-API-KEY": "invalid-key"})
    assert response.status_code == 401

    # Test POST endpoint with invalid API key
    job_config = {"name": "test-job", "cmd": "echo 'Hello, World!'", "imagename": "debian:latest"}
    response = client.post(
        "/api/toolforge/jobs/v1/tool/test-tool/jobs/",
        json=job_config,
        headers={"X-API-KEY": "invalid-key"}
    )
    assert response.status_code == 401

    # Test DELETE endpoint with invalid API key
    response = client.delete(
        "/api/toolforge/jobs/v1/tool/test-tool/jobs/job1",
        headers={"X-API-KEY": "invalid-key"}
    )
    assert response.status_code == 401


def test_missing_server_api_key():
    """Test that endpoints requiring authentication return 500 when API key is not set on server."""
    # Save the current API key
    original_api_key = os.environ.get("X_API_KEY")

    try:
        # Remove the API key from environment
        if "X_API_KEY" in os.environ:
            del os.environ["X_API_KEY"]

        # Test GET endpoint with valid client API key but missing server API key
        response = client.get("/api/toolforge/jobs/v1/tool/test-tool/jobs/", headers={"X-API-KEY": "any-key"})
        assert response.status_code == 500
        assert response.json()["detail"] == "API key not configured on server"

        # Test POST endpoint with valid client API key but missing server API key
        job_config = {"name": "test-job", "cmd": "echo 'Hello, World!'", "imagename": "debian:latest"}
        response = client.post(
            "/api/toolforge/jobs/v1/tool/test-tool/jobs/",
            json=job_config,
            headers={"X-API-KEY": "any-key"}
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "API key not configured on server"

        # Test DELETE endpoint with valid client API key but missing server API key
        response = client.delete(
            "/api/toolforge/jobs/v1/tool/test-tool/jobs/job1",
            headers={"X-API-KEY": "any-key"}
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "API key not configured on server"
    finally:
        # Restore the original API key
        if original_api_key:
            os.environ["X_API_KEY"] = original_api_key

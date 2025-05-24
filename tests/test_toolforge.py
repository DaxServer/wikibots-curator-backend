import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from curator import toolforge
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


def test_missing_api_key():
    """Test that endpoints requiring authentication return 403 when API key is missing."""
    # Test without API key
    response = client.get("/api/toolforge/jobs/v1/tool/test-tool/jobs/")
    assert response.status_code == 403


def test_invalid_api_key():
    """Test that endpoints requiring authentication return 401 when API key is invalid."""
    # Test with invalid API key
    response = client.get("/api/toolforge/jobs/v1/tool/test-tool/jobs/", headers={"X-API-KEY": "invalid-key"})
    assert response.status_code == 401


def test_missing_server_api_key():
    """Test that endpoints requiring authentication return 500 when API key is not set on server."""
    # Save the current API key
    original_api_key = os.environ.get("X_API_KEY")

    try:
        # Remove the API key from environment
        if "X_API_KEY" in os.environ:
            del os.environ["X_API_KEY"]

        # Test with valid client API key but missing server API key
        response = client.get("/api/toolforge/jobs/v1/tool/test-tool/jobs/", headers={"X-API-KEY": "any-key"})
        assert response.status_code == 500
        assert response.json()["detail"] == "API key not configured on server"
    finally:
        # Restore the original API key
        if original_api_key:
            os.environ["X_API_KEY"] = original_api_key

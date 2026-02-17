"""Tests for global exception handling."""

from fastapi import HTTPException
from fastapi.testclient import TestClient

from curator.main import app

client = TestClient(app, raise_server_exceptions=False)


# Test route handlers defined at module level
@app.get("/test-error")
def raise_error_route():
    raise ValueError("This is a test error")


@app.get("/test-http-error")
def raise_http_error_route():
    raise HTTPException(status_code=404, detail="Not Found Test")


def test_exception_handler():
    """Test that ValueError is caught and returns 500 with error message."""
    response = client.get("/test-error")
    assert response.status_code == 500
    data = response.json()
    assert data["detail"] == "This is a test error"
    assert "stacktrace" not in data


def test_http_exception_handler():
    """Test that HTTPException preserves status code and detail message."""
    response = client.get("/test-http-error")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "Not Found Test"
    assert "stacktrace" not in data

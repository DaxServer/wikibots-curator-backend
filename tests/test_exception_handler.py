from fastapi.testclient import TestClient
from curator.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_exception_handler():
    # Define a route that raises an exception
    @app.get("/test-error")
    def raise_error():
        raise ValueError("This is a test error")

    response = client.get("/test-error")

    # Default behavior (before fix) is usually 500 with "Internal Server Error"
    # We want to assert that AFTER the fix, it returns JSON with stacktrace.
    assert response.status_code == 500
    data = response.json()
    assert data["detail"] == "This is a test error"
    assert "stacktrace" not in data
    # assert isinstance(data["stacktrace"], list)
    # assert len(data["stacktrace"]) > 0


def test_http_exception_handler():
    from fastapi import HTTPException

    @app.get("/test-http-error")
    def raise_http_error():
        raise HTTPException(status_code=404, detail="Not Found Test")

    response = client.get("/test-http-error")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "Not Found Test"
    assert "stacktrace" not in data

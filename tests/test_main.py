import os
from fastapi.testclient import TestClient

from curator.main import app

# Set up test API key
os.environ["X_API_KEY"] = "test-api-key"

client = TestClient(app)


def test_root():
    """Test the root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the CuratorBot API"}

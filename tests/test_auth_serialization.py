import pytest
from mwoauth import AccessToken

from curator.app.auth import check_login


@pytest.mark.asyncio
async def test_check_login_with_list_token(mock_request):
    """Test login check when access_token is a list (simulating JSON deserialization)"""
    # Setup mock request session with user data and access_token as a list
    mock_request.session = {
        "user": {"username": "testuser", "sub": "user123"},
        "access_token": ["test_token", "test_secret"],
    }

    result = await check_login(mock_request)

    # Verify the result has an AccessToken object, not a list
    assert isinstance(result["access_token"], AccessToken)
    assert result["access_token"].key == "test_token"
    assert result["access_token"].secret == "test_secret"

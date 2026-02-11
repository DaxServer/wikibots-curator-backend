import pytest
from fastapi import HTTPException
from mwoauth import AccessToken

from curator.app.auth import check_login


@pytest.mark.asyncio
async def test_check_login_success(mock_request, mock_user):
    """Test successful login check"""
    # Setup mock request session with user data
    mock_request.session = {
        "user": {"username": "testuser", "sub": "user123"},
        "access_token": AccessToken("test_token", "test_secret"),
    }

    result = await check_login(mock_request)
    assert result["username"] == "testuser"
    assert result["userid"] == "user123"
    assert result["access_token"] == AccessToken("test_token", "test_secret")


@pytest.mark.asyncio
async def test_check_login_no_user_data(mock_request):
    """Test login check with no user data"""
    # Setup mock request session without user data
    mock_request.session = {}

    with pytest.raises(HTTPException) as exc_info:
        await check_login(mock_request)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_check_login_missing_username(mock_request):
    """Test login check with missing username"""
    # Setup mock request session with incomplete user data
    mock_request.session = {
        "user": {
            "sub": "user123"
            # Missing username
        },
        "access_token": ("test_token", "test_secret"),
    }

    with pytest.raises(HTTPException) as exc_info:
        await check_login(mock_request)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_check_login_missing_userid(mock_request):
    """Test login check with missing userid"""
    # Setup mock request session with incomplete user data
    mock_request.session = {
        "user": {
            "username": "testuser"
            # Missing sub (userid)
        },
        "access_token": "test_token",
    }

    with pytest.raises(HTTPException) as exc_info:
        await check_login(mock_request)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_check_login_missing_access_token(mock_request):
    """Test login check with missing access token"""
    # Setup mock request session without access token
    mock_request.session = {
        "user": {"username": "testuser", "sub": "user123"}
        # Missing access_token
    }

    with pytest.raises(HTTPException) as exc_info:
        await check_login(mock_request)

    assert exc_info.value.status_code == 401

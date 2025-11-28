import pytest
from fastapi import HTTPException, Request, status
from unittest.mock import Mock
from curator.app.auth import check_login
from curator.admin import check_admin


@pytest.mark.asyncio
async def test_check_login_success():
    mock_request = Mock(spec=Request)
    mock_request.session = {
        "user": {"username": "testuser", "sub": "user123"},
        "access_token": "valid_token",
    }

    result = await check_login(mock_request)
    assert result == {
        "username": "testuser",
        "userid": "user123",
        "access_token": "valid_token",
    }


@pytest.mark.asyncio
async def test_check_login_missing_username():
    mock_request = Mock(spec=Request)
    mock_request.session = {
        "user": {"sub": "user123"},
        "access_token": "valid_token",
    }

    with pytest.raises(HTTPException) as exc_info:
        await check_login(mock_request)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_check_login_missing_userid():
    mock_request = Mock(spec=Request)
    mock_request.session = {
        "user": {"username": "testuser"},
        "access_token": "valid_token",
    }

    with pytest.raises(HTTPException) as exc_info:
        await check_login(mock_request)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_check_login_missing_token():
    mock_request = Mock(spec=Request)
    mock_request.session = {
        "user": {"username": "testuser", "sub": "user123"},
    }

    with pytest.raises(HTTPException) as exc_info:
        await check_login(mock_request)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_check_login_empty_session():
    mock_request = Mock(spec=Request)
    mock_request.session = {}

    with pytest.raises(HTTPException) as exc_info:
        await check_login(mock_request)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_check_admin_success():
    mock_request = Mock(spec=Request)
    mock_request.session = {
        "user": {"username": "DaxServer"},
    }

    # Should not raise exception
    check_admin(mock_request)


def test_check_admin_forbidden():
    mock_request = Mock(spec=Request)
    mock_request.session = {
        "user": {"username": "OtherUser"},
    }

    with pytest.raises(HTTPException) as exc_info:
        check_admin(mock_request)
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


def test_check_admin_no_user():
    mock_request = Mock(spec=Request)
    mock_request.session = {}

    with pytest.raises(HTTPException) as exc_info:
        check_admin(mock_request)
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

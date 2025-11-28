import pytest
from unittest.mock import Mock, patch
from fastapi import HTTPException, status
from curator.admin import (
    admin_get_batches,
    admin_get_users,
    admin_get_upload_requests,
)


@pytest.fixture
def mock_session_fixture():
    mock_session = Mock()
    yield mock_session
    mock_session.reset_mock()


@pytest.fixture
def mock_request_admin():
    req = Mock()
    req.session = {
        "user": {"username": "DaxServer", "sub": "user123"},
    }
    return req


@pytest.fixture
def mock_request_user():
    req = Mock()
    req.session = {
        "user": {"username": "testuser", "sub": "user456"},
    }
    return req


@pytest.mark.asyncio
async def test_admin_get_batches_success(mock_request_admin, mock_session_fixture):
    with (
        patch("curator.admin.get_batches") as mock_get_batches,
        patch("curator.admin.count_batches") as mock_count_batches,
    ):
        mock_get_batches.return_value = []
        mock_count_batches.return_value = 0

        result = await admin_get_batches(
            mock_request_admin, page=1, limit=100, session=mock_session_fixture
        )

        mock_get_batches.assert_called_once_with(
            mock_session_fixture, offset=0, limit=100
        )
        mock_count_batches.assert_called_once_with(mock_session_fixture)
        assert result == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_admin_get_users_success(mock_request_admin, mock_session_fixture):
    with (
        patch("curator.admin.get_users") as mock_get_users,
        patch("curator.admin.count_users") as mock_count_users,
    ):
        mock_get_users.return_value = []
        mock_count_users.return_value = 0

        result = await admin_get_users(
            mock_request_admin, page=1, limit=100, session=mock_session_fixture
        )

        mock_get_users.assert_called_once_with(
            mock_session_fixture, offset=0, limit=100
        )
        mock_count_users.assert_called_once_with(mock_session_fixture)
        assert result == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_admin_get_upload_requests_success(
    mock_request_admin, mock_session_fixture
):
    with (
        patch("curator.admin.get_all_upload_requests") as mock_get_all_upload_requests,
        patch(
            "curator.admin.count_all_upload_requests"
        ) as mock_count_all_upload_requests,
    ):
        mock_get_all_upload_requests.return_value = []
        mock_count_all_upload_requests.return_value = 0

        result = await admin_get_upload_requests(
            mock_request_admin, page=1, limit=100, session=mock_session_fixture
        )

        mock_get_all_upload_requests.assert_called_once_with(
            mock_session_fixture, offset=0, limit=100
        )
        mock_count_all_upload_requests.assert_called_once_with(mock_session_fixture)
        assert result == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_admin_unauthorized(mock_request_user, mock_session_fixture):
    with pytest.raises(HTTPException) as exc_info:
        await admin_get_batches(
            mock_request_user, page=1, limit=100, session=mock_session_fixture
        )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    with pytest.raises(HTTPException) as exc_info:
        await admin_get_users(
            mock_request_user, page=1, limit=100, session=mock_session_fixture
        )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    with pytest.raises(HTTPException) as exc_info:
        await admin_get_upload_requests(
            mock_request_user, page=1, limit=100, session=mock_session_fixture
        )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

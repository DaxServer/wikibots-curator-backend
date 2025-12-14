from unittest.mock import Mock, patch

import pytest

from curator.admin import (
    admin_get_batches,
    admin_get_upload_requests,
    admin_get_users,
)


@pytest.fixture
def mock_session_fixture():
    mock_session = Mock()
    yield mock_session
    mock_session.reset_mock()


@pytest.mark.asyncio
async def test_admin_get_batches_success(mock_session_fixture):
    with (
        patch("curator.admin.get_batches") as mock_get_batches,
        patch("curator.admin.count_batches") as mock_count_batches,
    ):
        mock_get_batches.return_value = []
        mock_count_batches.return_value = 0

        result = await admin_get_batches(
            page=1, limit=100, session=mock_session_fixture
        )

        mock_get_batches.assert_called_once_with(
            mock_session_fixture, offset=0, limit=100
        )
        mock_count_batches.assert_called_once_with(mock_session_fixture)
        assert result == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_admin_get_users_success(mock_session_fixture):
    with (
        patch("curator.admin.get_users") as mock_get_users,
        patch("curator.admin.count_users") as mock_count_users,
    ):
        mock_get_users.return_value = []
        mock_count_users.return_value = 0

        result = await admin_get_users(page=1, limit=100, session=mock_session_fixture)

        mock_get_users.assert_called_once_with(
            mock_session_fixture, offset=0, limit=100
        )
        mock_count_users.assert_called_once_with(mock_session_fixture)
        assert result == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_admin_get_upload_requests_success(mock_session_fixture):
    with (
        patch("curator.admin.get_all_upload_requests") as mock_get_all_upload_requests,
        patch(
            "curator.admin.count_all_upload_requests"
        ) as mock_count_all_upload_requests,
    ):
        mock_get_all_upload_requests.return_value = []
        mock_count_all_upload_requests.return_value = 0

        result = await admin_get_upload_requests(
            page=1, limit=100, session=mock_session_fixture
        )

        mock_get_all_upload_requests.assert_called_once_with(
            mock_session_fixture, offset=0, limit=100
        )
        mock_count_all_upload_requests.assert_called_once_with(mock_session_fixture)
        assert result == {"items": [], "total": 0}

import pytest
from unittest.mock import AsyncMock
from cashews import Command
from cashews.exceptions import UnSecureDataError

from curator.app.config import integrity_middleware


@pytest.mark.asyncio
async def test_integrity_failure_handles_get_command():
    """
    Test that when Command.GET raises UnSecureDataError:
    1. The exception is caught.
    2. The cache key is deleted (invalidated).
    3. The default value (sentinel) is returned to simulate a cache miss.
    """
    # Setup
    key = "test:key"
    default_sentinel = object()  # Simulate NOT_FOUND sentinel

    # Mock the next link in the chain (which would normally perform the cache GET)
    # It raises UnSecureDataError to simulate data corruption
    async def mock_call(*args, **kwargs):
        raise UnSecureDataError("Tampered Data")

    mock_backend = AsyncMock()

    # Execute middleware
    result = await integrity_middleware(
        mock_call, Command.GET, mock_backend, key, default=default_sentinel
    )

    # Assertions
    # 1. Should return the default sentinel (simulating miss)
    assert result is default_sentinel

    # 2. Should attempt to delete the compromised key
    mock_backend.delete.assert_called_once_with(key)


@pytest.mark.asyncio
async def test_integrity_failure_handles_args_key():
    """Test key extraction from args."""
    key = "test:key:args"
    default_sentinel = object()

    async def mock_call(*args, **kwargs):
        raise UnSecureDataError("Tampered")

    mock_backend = AsyncMock()

    # Pass key as first arg
    result = await integrity_middleware(
        mock_call,
        Command.GET,
        mock_backend,
        key,
        default_sentinel,  # args[1] is default if present
    )

    assert result is default_sentinel
    mock_backend.delete.assert_called_once_with(key)


@pytest.mark.asyncio
async def test_non_get_integrity_failure_raises():
    """Test that UnSecureDataError propagates for non-GET commands."""

    async def mock_call(*args, **kwargs):
        raise UnSecureDataError("Tampered")

    mock_backend = AsyncMock()

    with pytest.raises(UnSecureDataError):
        await integrity_middleware(
            mock_call, Command.SET, mock_backend, "key", value="val"
        )

    # Should NOT delete for SET (or at least logic doesn't reach there)
    mock_backend.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_failure_propagates():
    """
    Test that if the invalidation (delete) fails, the exception propagates.
    We do NOT want to swallow backend errors like ConnectionError during recovery.
    """

    async def mock_call(*args, **kwargs):
        raise UnSecureDataError("Tampered")

    mock_backend = AsyncMock()
    mock_backend.delete.side_effect = Exception("Redis Down")

    # Should raise the deletion exception
    with pytest.raises(Exception, match="Redis Down"):
        await integrity_middleware(
            mock_call, Command.GET, mock_backend, "key", default=None
        )

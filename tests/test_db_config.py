"""Tests for database configuration."""

from sqlalchemy.pool import QueuePool

from curator.db.engine import engine


def test_engine_pool_configuration():
    """Test that database engine pool is configured with correct settings."""
    pool = engine.pool
    assert pool._pre_ping is True
    assert pool._recycle == 280
    assert isinstance(pool, QueuePool)
    assert pool.size() == 5
    assert pool._max_overflow == 10

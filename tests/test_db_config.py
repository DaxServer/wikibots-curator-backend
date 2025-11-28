from curator.app.db import engine


def test_engine_pool_configuration():
    # Check if pool_pre_ping is enabled
    assert engine.pool._pre_ping is True
    # Check if pool_recycle is set to 280 seconds
    assert engine.pool._recycle == 280

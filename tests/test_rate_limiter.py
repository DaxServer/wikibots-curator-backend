"""Tests for rate limiting module."""

from unittest.mock import MagicMock

import pytest

from curator.app.rate_limiter import (
    RateLimitInfo,
    get_next_upload_delay,
    get_rate_limit_for_batch,
)


@pytest.fixture(autouse=True)
def setup_redis_mock(mocker):
    """Set up redis_client mock for all tests."""
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.setex.return_value = True
    mock_redis.delete.return_value = 1
    mocker.patch("curator.app.rate_limiter.redis_client", mock_redis)
    return mock_redis


def get_redis_mock(mocker):
    """Get the redis_client mock."""
    from curator.app import rate_limiter

    return rate_limiter.redis_client


class TestGetRateLimitForBatch:
    """Tests for get_rate_limit_for_batch."""

    def test_normal_user_detected(self, mocker):
        """Test that normal users get default rate limit"""
        mock_client = MagicMock()
        mock_client.is_privileged.return_value = False

        rate_limit = get_rate_limit_for_batch("user123", client=mock_client)

        mock_client.is_privileged.assert_called_once()
        assert rate_limit.is_privileged is False
        assert rate_limit.uploads_per_period == 4
        assert rate_limit.period_seconds == 60

    def test_privileged_user_detected(self, mocker):
        """Test that privileged users (patroller) are detected."""
        mock_client = MagicMock()
        mock_client.is_privileged.return_value = True

        rate_limit = get_rate_limit_for_batch("user123", client=mock_client)

        assert rate_limit.is_privileged is True
        assert rate_limit.uploads_per_period == 999
        assert rate_limit.period_seconds == 1

    def test_sysop_user_detected(self, mocker):
        """Test that sysop users are detected as privileged."""
        mock_client = MagicMock()
        mock_client.is_privileged.return_value = True

        rate_limit = get_rate_limit_for_batch("user123", client=mock_client)

        assert rate_limit.is_privileged is True
        assert rate_limit.uploads_per_period == 999
        assert rate_limit.period_seconds == 1

    def test_api_failure_uses_defaults(self, mocker):
        """Test that API failure falls back to defaults."""
        mock_client = MagicMock()
        mock_client.is_privileged.side_effect = Exception("API Error")

        rate_limit = get_rate_limit_for_batch("user123", client=mock_client)

        assert rate_limit.is_privileged is False
        assert rate_limit.uploads_per_period == 4
        assert rate_limit.period_seconds == 60


class TestGetNextUploadDelay:
    """Tests for upload delay calculation."""

    def test_privileged_user_no_delay(self, mocker):
        """Test that privileged users have no delay."""
        mock_redis = get_redis_mock(mocker)
        rate_limit = RateLimitInfo(
            uploads_per_period=999, period_seconds=1, is_privileged=True
        )

        delay = get_next_upload_delay("user123", rate_limit)

        assert delay == 0.0
        mock_redis.get.assert_not_called()
        mock_redis.setex.assert_not_called()

    def test_normal_user_first_upload(self, mocker):
        """Test first upload has no delay."""
        mock_redis = get_redis_mock(mocker)
        mock_redis.get.return_value = None
        rate_limit = RateLimitInfo(
            uploads_per_period=4, period_seconds=60, is_privileged=False
        )

        delay = get_next_upload_delay("user123", rate_limit)

        assert delay == 0.0
        mock_redis.setex.assert_called_once()

    def test_normal_user_subsequent_uploads_spaced(self, mocker):
        """Test that uploads are properly spaced."""
        mock_redis = get_redis_mock(mocker)
        rate_limit = RateLimitInfo(
            uploads_per_period=4, period_seconds=60, is_privileged=False
        )

        # Mock time to control the flow
        mock_time = mocker.patch("curator.app.rate_limiter.time")
        mock_time.time.return_value = 100.0

        # First upload
        mock_redis.get.return_value = None
        delay1 = get_next_upload_delay("user123", rate_limit)
        assert delay1 == 0.0

        # Get the next_available time that was set (100 + 15 = 115)
        call_args = mock_redis.setex.call_args
        # setex(name, ttl, value) - value is at index 2
        next_available = float(call_args[0][2])

        # Simulate second call - time hasn't advanced much
        mock_time.time.return_value = 100.1
        mock_redis.get.return_value = str(next_available)
        delay2 = get_next_upload_delay("user123", rate_limit)

        # Should have delay close to 15 seconds (115 - 100.1 = 14.9)
        assert delay2 > 14.0
        assert delay2 <= 15.0

    def test_multiple_uploads_incremental_delays(self, mocker):
        """Test that multiple uploads get incremental delays."""
        mock_redis = get_redis_mock(mocker)
        rate_limit = RateLimitInfo(
            uploads_per_period=4, period_seconds=60, is_privileged=False
        )

        # Mock time to control the flow
        mock_time = mocker.patch("curator.app.rate_limiter.time")
        mock_time.time.return_value = 100.0

        # Upload 1
        mock_redis.get.return_value = None
        delay1 = get_next_upload_delay("user123", rate_limit)
        assert delay1 == 0.0

        # Manually update redis mock to simulate state for next call
        # Next available = 100 + 15 = 115
        mock_redis.get.return_value = "115.0"

        # Upload 2 (immediate)
        delay2 = get_next_upload_delay("user123", rate_limit)
        # Should wait 15s (until 115)
        assert delay2 == 15.0

        # New next available should be 115 + 15 = 130
        call_args = mock_redis.setex.call_args
        assert float(call_args[0][2]) == 130.0

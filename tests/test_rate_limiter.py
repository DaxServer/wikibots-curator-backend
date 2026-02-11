"""Tests for rate limiting module."""

import time
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
    """Tests for get_rate_limit_for_batch (takes site as parameter)."""

    def test_normal_user_detected(self, mocker):
        """Test that normal users get default rate limit"""
        mock_site = MagicMock()
        mock_site.has_group = MagicMock(return_value=False)
        rate_limit = get_rate_limit_for_batch(mock_site, "user123")

        assert rate_limit.is_privileged is False
        assert rate_limit.uploads_per_period == 4
        assert rate_limit.period_seconds == 60

    def test_privileged_user_detected(self, mocker):
        """Test that privileged users (patroller) are detected."""
        mock_site = MagicMock()
        mock_site.has_group = MagicMock(side_effect=lambda g: g == "patroller")

        rate_limit = get_rate_limit_for_batch(mock_site, "user123")

        assert rate_limit.is_privileged is True
        assert rate_limit.uploads_per_period == 999
        assert rate_limit.period_seconds == 1

    def test_sysop_user_detected(self, mocker):
        """Test that sysop users are detected as privileged."""
        mock_site = MagicMock()
        mock_site.has_group = MagicMock(side_effect=lambda g: g == "sysop")

        rate_limit = get_rate_limit_for_batch(mock_site, "user123")

        assert rate_limit.is_privileged is True
        assert rate_limit.uploads_per_period == 999
        assert rate_limit.period_seconds == 1

    def test_api_failure_uses_defaults(self, mocker):
        """Test that API failure falls back to defaults."""
        mock_site = MagicMock()
        mock_site.has_group = MagicMock(side_effect=Exception("API Error"))

        rate_limit = get_rate_limit_for_batch(mock_site, "user123")

        assert rate_limit.is_privileged is False
        assert rate_limit.uploads_per_period == 4
        assert rate_limit.period_seconds == 60

    def test_has_group_failure_uses_defaults(self, mocker):
        """Test that failure to check user groups falls back to defaults."""
        mock_site = MagicMock()
        mock_site.has_group = MagicMock(side_effect=Exception("Groups error"))

        rate_limit = get_rate_limit_for_batch(mock_site, "user123")

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

        # Upload 2 - should have delay
        # setex(name, ttl, value) - value is at index 2
        next_available = float(mock_redis.setex.call_args[0][2])
        # Advance time to just before next_available
        mock_time.time.return_value = next_available - 0.1
        mock_redis.get.return_value = str(next_available)
        delay2 = get_next_upload_delay("user123", rate_limit)
        # Should have small delay (~0.1 seconds)
        assert delay2 > 0
        assert delay2 < 1.0

        # Upload 3 - advance time again
        next_available = float(mock_redis.setex.call_args[0][2])
        mock_time.time.return_value = next_available - 0.1
        mock_redis.get.return_value = str(next_available)
        delay3 = get_next_upload_delay("user123", rate_limit)
        # Should have small delay (~0.1 seconds)
        assert delay3 > 0
        assert delay3 < 1.0

    def test_delay_never_negative(self, mocker):
        """Test that delay is never negative (even if Redis has old timestamp)."""
        mock_redis = get_redis_mock(mocker)
        old_timestamp = time.time() - 1000  # 1000 seconds ago
        mock_redis.get.return_value = str(old_timestamp)
        rate_limit = RateLimitInfo(
            uploads_per_period=4, period_seconds=60, is_privileged=False
        )

        delay = get_next_upload_delay("user123", rate_limit)

        assert delay >= 0.0


class TestIntegration:
    """Integration tests for rate limiting."""

    def test_single_slice_spacing(self, mocker):
        """Test spacing for a single slice with multiple items."""
        mock_redis = get_redis_mock(mocker)
        rate_limit = RateLimitInfo(
            uploads_per_period=4, period_seconds=60, is_privileged=False
        )

        # Mock time to control the flow
        mock_time = mocker.patch("curator.app.rate_limiter.time")

        delays = []
        next_available = 100.0  # Start time
        for i in range(10):
            if i == 0:
                mock_time.time.return_value = 100.0
                mock_redis.get.return_value = None
            else:
                # Set time to just before the next available slot
                mock_time.time.return_value = next_available - 0.01
                mock_redis.get.return_value = str(next_available)

            delay = get_next_upload_delay("user123", rate_limit)
            delays.append(delay)

            # Get the new next_available time for next iteration
            # setex(name, ttl, value) - value is at index 2
            next_available = float(mock_redis.setex.call_args[0][2])

        # First upload has no delay, rest should have small delays
        assert delays[0] == 0.0
        for delay in delays[1:]:
            assert delay >= 0, f"Delay {delays.index(delay)} should be non-negative"
            # With proper time advancement, delays should be small
            assert delay < 1.0, f"Delay {delays.index(delay)} should be small"

    def test_multiple_slice_continuity(self, mocker):
        """Test that multiple slices continue spacing correctly."""
        mock_redis = get_redis_mock(mocker)
        rate_limit = RateLimitInfo(
            uploads_per_period=4, period_seconds=60, is_privileged=False
        )

        # Mock time to control the flow
        mock_time = mocker.patch("curator.app.rate_limiter.time")

        # Slice 1: items 0-17
        slice1_delays = []
        for i in range(18):
            if i == 0:
                mock_time.time.return_value = 100.0
                mock_redis.get.return_value = None
            else:
                mock_time.time.return_value = 100.0 + (i * 0.01)
                next_available = float(mock_redis.setex.call_args[0][2])
                mock_redis.get.return_value = str(next_available)

            delay = get_next_upload_delay("user123", rate_limit)
            slice1_delays.append(delay)

        # Slice 2: items 18-35 (should continue from where slice 1 left off)
        slice2_delays = []
        for i in range(18):
            mock_time.time.return_value = 100.0 + (18 + i) * 0.01
            next_available = float(mock_redis.setex.call_args[0][2])
            mock_redis.get.return_value = str(next_available)

            delay = get_next_upload_delay("user123", rate_limit)
            slice2_delays.append(delay)

        # Verify spacing - first has no delay, rest have delays
        assert slice1_delays[0] == 0.0
        for delay in slice1_delays[1:]:
            assert delay > 0, "Slice 1 delays should be positive"
        for delay in slice2_delays:
            assert delay > 0, "Slice 2 delays should be positive"

"""Tests for rate limiting module."""

from unittest.mock import MagicMock

import pytest

from curator.core import rate_limiter as rate_limiter_module
from curator.core.rate_limiter import (
    _NO_RATE_LIMIT,
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
    mock_redis.delete.return_value = 1
    mocker.patch("curator.core.rate_limiter.redis_client", mock_redis)
    return mock_redis


def get_redis_mock(mocker):
    """Get the redis_client mock."""
    return rate_limiter_module.redis_client


class TestGetRateLimitForBatch:
    """Tests for get_rate_limit_for_batch."""

    def test_upload_rate_is_bottleneck(self):
        """Upload rate is used when it is more restrictive than edit/2"""
        mock_client = MagicMock()
        # upload: 380/4320s ≈ 0.088/s; edit/2: 450/180s = 2.5/s → upload wins
        mock_client.get_user_rate_limits.return_value = (
            {
                "upload": {"user": {"hits": 380, "seconds": 4320}},
                "edit": {"user": {"hits": 900, "seconds": 180}},
            },
            [],
        )

        rate_limit = get_rate_limit_for_batch("user123", client=mock_client)

        assert rate_limit.uploads_per_period == 380
        assert rate_limit.period_seconds == 4320

    def test_edit_rate_is_bottleneck(self):
        """Edit/2 rate is used when it is more restrictive than upload"""
        mock_client = MagicMock()
        # upload: 100/10s = 10/s; edit/2: 5/10s = 0.5/s → edit/2 wins
        mock_client.get_user_rate_limits.return_value = (
            {
                "upload": {"user": {"hits": 100, "seconds": 10}},
                "edit": {"user": {"hits": 10, "seconds": 10}},
            },
            [],
        )

        rate_limit = get_rate_limit_for_batch("user123", client=mock_client)

        assert rate_limit.uploads_per_period == 5
        assert rate_limit.period_seconds == 10

    def test_multiple_groups_takes_most_permissive_per_action(self):
        """Most permissive group limit is used per action before comparing"""
        mock_client = MagicMock()
        # upload patroller: 999/1s = 999/s (beats user 380/4320)
        # edit patroller: 1500/180s ≈ 8.33/s (beats user 900/180 = 5/s)
        # edit/2 patroller: 750/180 ≈ 4.17/s → bottleneck vs 999/s upload
        mock_client.get_user_rate_limits.return_value = (
            {
                "upload": {
                    "user": {"hits": 380, "seconds": 4320},
                    "patroller": {"hits": 999, "seconds": 1},
                },
                "edit": {
                    "user": {"hits": 900, "seconds": 180},
                    "patroller": {"hits": 1500, "seconds": 180},
                },
            },
            ["patrol"],
        )

        rate_limit = get_rate_limit_for_batch("user123", client=mock_client)

        assert rate_limit.uploads_per_period == 750
        assert rate_limit.period_seconds == 180

    def test_noratelimit_user_skips_rate_limiting(self):
        """User with noratelimit right gets effectively unlimited rate"""
        mock_client = MagicMock()
        mock_client.get_user_rate_limits.return_value = ({}, ["noratelimit", "edit"])

        rate_limit = get_rate_limit_for_batch("user123", client=mock_client)

        assert rate_limit == _NO_RATE_LIMIT

    def test_edit_odd_hits_clamps_to_minimum(self):
        """Edit hits=1 (1//2=0) is clamped to 1 to prevent ZeroDivisionError"""
        mock_client = MagicMock()
        # upload: 100/10s = 10/s; edit: 1/10s → edit/2 = max(1,0) = 1/10s → bottleneck
        mock_client.get_user_rate_limits.return_value = (
            {
                "upload": {"user": {"hits": 100, "seconds": 10}},
                "edit": {"user": {"hits": 1, "seconds": 10}},
            },
            [],
        )

        rate_limit = get_rate_limit_for_batch("user123", client=mock_client)

        assert rate_limit.uploads_per_period == 1
        assert rate_limit.period_seconds == 10

    def test_api_failure_uses_defaults(self):
        """API failure falls back to defaults."""
        mock_client = MagicMock()
        mock_client.get_user_rate_limits.side_effect = Exception("API Error")

        rate_limit = get_rate_limit_for_batch("user123", client=mock_client)

        assert rate_limit.uploads_per_period == 4
        assert rate_limit.period_seconds == 60


class TestGetNextUploadDelay:
    """Tests for upload delay calculation."""

    def test_first_upload_has_no_delay(self, mocker):
        """Test first upload has no delay."""
        mock_redis = get_redis_mock(mocker)
        mock_redis.get.return_value = None
        rate_limit = RateLimitInfo(uploads_per_period=4, period_seconds=60)

        delay = get_next_upload_delay("user123", rate_limit)

        assert delay == 0.0
        mock_redis.set.assert_called_once()

    def test_subsequent_uploads_are_spaced(self, mocker):
        """Test that uploads are properly spaced."""
        mock_redis = get_redis_mock(mocker)
        rate_limit = RateLimitInfo(uploads_per_period=4, period_seconds=60)

        # Mock time to control the flow
        mock_time = mocker.patch("curator.core.rate_limiter.time")
        mock_time.time.return_value = 100.0

        # First upload
        mock_redis.get.return_value = None
        delay1 = get_next_upload_delay("user123", rate_limit)
        assert delay1 == 0.0

        # Get the next_available time that was set (100 + 22.5 = 122.5)
        call_args = mock_redis.set.call_args
        next_available = float(call_args[0][1])

        # Simulate second call - time hasn't advanced much
        mock_time.time.return_value = 100.1
        mock_redis.get.return_value = str(next_available)
        delay2 = get_next_upload_delay("user123", rate_limit)

        # Should have delay close to 22.5 seconds (122.5 - 100.1 = 22.4)
        assert delay2 > 21.0
        assert delay2 <= 22.5

    def test_multiple_uploads_incremental_delays(self, mocker):
        """Test that multiple uploads get incremental delays."""
        mock_redis = get_redis_mock(mocker)
        rate_limit = RateLimitInfo(uploads_per_period=4, period_seconds=60)

        # Mock time to control the flow
        mock_time = mocker.patch("curator.core.rate_limiter.time")
        mock_time.time.return_value = 100.0

        # Upload 1
        mock_redis.get.return_value = None
        delay1 = get_next_upload_delay("user123", rate_limit)
        assert delay1 == 0.0

        # Manually update redis mock to simulate state for next call
        # Next available = 100 + 22.5 = 122.5
        mock_redis.get.return_value = "122.5"

        # Upload 2 (immediate)
        delay2 = get_next_upload_delay("user123", rate_limit)
        # Should wait 22.5s (until 122.5)
        assert delay2 == 22.5

        # New next available should be 122.5 + 22.5 = 145.0
        call_args = mock_redis.set.call_args
        assert float(call_args[0][1]) == 145.0

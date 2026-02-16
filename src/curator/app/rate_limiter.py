"""Rate limiting for Wikimedia Commons uploads.

Checks if user is privileged (patroller/sysop) using MediaWikiClient.get_user_groups()
and spaces out Celery task enqueueing to match the allowed rate, preventing API throttling.
"""

import logging
import time
from dataclasses import dataclass

from curator.app.config import (
    RATE_LIMIT_DEFAULT_NORMAL,
    RATE_LIMIT_DEFAULT_PERIOD,
    redis_client,
)
from curator.app.mediawiki_client import MediaWikiClient

logger = logging.getLogger(__name__)

# Cache key template for tracking next available upload slot
_NEXT_AVAILABLE_KEY = "ratelimit:{userid}:next_available"


@dataclass
class RateLimitInfo:
    """Rate limit information for a user"""

    uploads_per_period: int
    period_seconds: int
    is_privileged: bool


# Privileged user rate limit (effectively no limit)
_PRIVILEGED_LIMIT = RateLimitInfo(
    uploads_per_period=999, period_seconds=1, is_privileged=True
)

# User groups that are exempt from rate limiting
_PRIVILEGED_GROUPS = {"patroller", "sysop"}


def get_rate_limit_for_batch(
    userid: str,
    client: MediaWikiClient,
) -> RateLimitInfo:
    """
    Get rate limit info for a user.

    Uses MediaWiki API via MediaWikiClient.
    """
    try:
        is_privileged = client.is_privileged()

        logger.info(f"[rate_limiter] User {userid} privileged={is_privileged}")

        if is_privileged:
            return _PRIVILEGED_LIMIT
    except Exception as e:
        logger.warning(f"[rate_limiter] Failed to fetch user groups: {e}")

    # Default rate limit for normal users
    return RateLimitInfo(
        uploads_per_period=RATE_LIMIT_DEFAULT_NORMAL,
        period_seconds=RATE_LIMIT_DEFAULT_PERIOD,
        is_privileged=False,
    )


def get_next_upload_delay(userid: str, rate_limit: RateLimitInfo) -> float:
    """Calculate delay for next upload based on rate limit.

    For privileged users, returns 0.0 (no delay).
    For normal users, tracks next available slot in Redis and returns delay.
    """
    if rate_limit.is_privileged:
        return 0.0

    cache_key = _NEXT_AVAILABLE_KEY.format(userid=userid)
    current_time = time.time()

    # Get next available slot from Redis
    next_available_str = redis_client.get(cache_key)
    if next_available_str and isinstance(next_available_str, str):
        next_available = float(next_available_str)
    else:
        next_available = current_time

    # Calculate delay and spacing
    delay = max(0.0, next_available - current_time)
    spacing = rate_limit.period_seconds / rate_limit.uploads_per_period

    # Update next available slot (1 hour TTL)
    new_next_available = max(current_time, next_available) + spacing
    redis_client.setex(cache_key, 3600, str(new_next_available))

    logger.debug(
        f"[rate_limiter] User {userid}: delay={delay:.2f}s, "
        f"next_available={new_next_available:.2f}"
    )

    return delay

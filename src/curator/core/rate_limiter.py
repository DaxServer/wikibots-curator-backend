"""Rate limiting for Wikimedia Commons uploads.

Determines rate limits by fetching upload and edit limits from the MediaWiki
userinfo API and taking the most restrictive effective rate. Each upload requires
2 edit API calls (SDC apply + null edit), so the edit limit is halved before
comparing against the upload limit. Users with the 'noratelimit' right are exempt
and receive _NO_RATE_LIMIT.
"""

import logging
import time
from dataclasses import dataclass

from curator.core.config import (
    RATE_LIMIT_DEFAULT_NORMAL,
    RATE_LIMIT_DEFAULT_PERIOD,
    redis_client,
)
from curator.mediawiki.client import MediaWikiClient

logger = logging.getLogger(__name__)

# Cache key template for tracking next available upload slot
_NEXT_AVAILABLE_KEY = "ratelimit:{userid}:next_available"


@dataclass
class RateLimitInfo:
    """Rate limit information for a user"""

    uploads_per_period: int
    period_seconds: int


# For users exempt from rate limiting (have 'noratelimit' right)
_NO_RATE_LIMIT = RateLimitInfo(uploads_per_period=9999, period_seconds=60)


def _most_permissive(limits: dict[str, dict]) -> tuple[int, int] | None:
    """Return (hits, seconds) for the group with the highest hits/second rate."""
    best: tuple[int, int] | None = None
    best_rate = -1.0
    for limit in limits.values():
        rate = limit["hits"] / limit["seconds"]
        if rate > best_rate:
            best_rate = rate
            best = (limit["hits"], limit["seconds"])
    return best


def _more_restrictive(
    a: tuple[int, int] | None, b: tuple[int, int] | None
) -> tuple[int, int] | None:
    """Return the tuple with the lower hits/second rate (more restrictive)."""
    if a is None:
        return b
    if b is None:
        return a
    return a if a[0] / a[1] <= b[0] / b[1] else b


def get_rate_limit_for_batch(userid: str, client: MediaWikiClient) -> RateLimitInfo:
    """Get rate limit info for a user from the MediaWiki userinfo API."""
    try:
        rate_limits, rights = client.get_user_rate_limits()

        if "noratelimit" in rights:
            logger.info(f"[rate_limiter] User {userid} is exempt from rate limiting")
            return _NO_RATE_LIMIT

        upload_limits = rate_limits.get("upload", {})
        edit_limits = rate_limits.get("edit", {})

        best_upload = _most_permissive(upload_limits)
        best_edit = _most_permissive(edit_limits)

        # Each upload costs 2 edits (SDC + null edit), so halve the edit limit.
        # Clamp to minimum of 1 to avoid ZeroDivisionError when hits is odd (e.g. 1//2=0)
        adjusted_edit = (max(1, best_edit[0] // 2), best_edit[1]) if best_edit else None

        effective = _more_restrictive(best_upload, adjusted_edit)

        if effective is None:
            logger.info(
                f"[rate_limiter] User {userid} has no rate limits, treating as exempt"
            )
            return _NO_RATE_LIMIT

        logger.info(
            f"[rate_limiter] User {userid} effective rate: "
            f"{effective[0]}/{effective[1]}s"
        )
        return RateLimitInfo(
            uploads_per_period=effective[0],
            period_seconds=effective[1],
        )
    except Exception as e:
        logger.warning(f"[rate_limiter] Failed to fetch rate limits: {e}")

    return RateLimitInfo(
        uploads_per_period=RATE_LIMIT_DEFAULT_NORMAL,
        period_seconds=RATE_LIMIT_DEFAULT_PERIOD,
    )


def get_next_upload_delay(userid: str, rate_limit: RateLimitInfo) -> float:
    """Calculate delay for next upload based on rate limit."""
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

    # Update next available slot
    new_next_available = max(current_time, next_available) + spacing
    redis_client.set(cache_key, str(new_next_available))

    logger.debug(
        f"[rate_limiter] User {userid}: delay={delay:.2f}s, "
        f"next_available={new_next_available:.2f}"
    )

    return delay

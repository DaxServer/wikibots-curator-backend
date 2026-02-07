import logging
import os
from enum import Enum

import redis
from cryptography.fernet import Fernet

OAUTH_KEY = os.environ.get("CURATOR_OAUTH1_KEY")
OAUTH_SECRET = os.environ.get("CURATOR_OAUTH1_SECRET")


USER_AGENT = (
    "Curator / Toolforge curator.toolforge.org / Wikimedia Commons User:DaxServer"
)

TEST_URLS = {
    "index_url": "https://test.wikipedia.org/w/index.php",
    "base_url": "https://test.wikipedia.org/w/api.php",
    "authorize_url": "https://test.wikipedia.org/w/rest.php/oauth2/authorize",
    "access_token_url": "https://test.wikipedia.org/w/rest.php/oauth2/access_token",
    "profile_url": "https://test.wikipedia.org/w/rest.php/oauth2/resource/profile",
}

PROD_URLS = {
    "index_url": "https://commons.wikimedia.org/w/index.php",
    "base_url": "https://commons.wikimedia.org/w/api.php",
    "authorize_url": "https://commons.wikimedia.org/w/rest.php/oauth2/authorize",
    "access_token_url": "https://commons.wikimedia.org/w/rest.php/oauth2/access_token",
    "profile_url": "https://commons.wikimedia.org/w/rest.php/oauth2/resource/profile",
}

URLS = PROD_URLS

TOKEN_ENCRYPTION_KEY = os.environ.get(
    "TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode()
)
WCQS_OAUTH_TOKEN = os.getenv("WCQS_OAUTH_TOKEN", "WCQS_OAUTH_TOKEN")
MAPILLARY_API_TOKEN = os.getenv("MAPILLARY_API_TOKEN", "MAPILLARY_API_TOKEN")
FLICKR_API_KEY = os.getenv("FLICKR_API_KEY", "FLICKR_API_KEY")

_REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
_REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
_REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
if _REDIS_PASSWORD:
    REDIS_URL = f"redis://:{_REDIS_PASSWORD}@{_REDIS_HOST}:{_REDIS_PORT}"
else:
    REDIS_URL = f"redis://{_REDIS_HOST}:{_REDIS_PORT}"

redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

CELERY_CONCURRENCY = int(os.getenv("CELERY_CONCURRENCY", 2))
CELERY_MAXIMUM_WAIT_TIME = int(os.getenv("CELERY_MAXIMUM_WAIT_TIME", 60 * 4))  # minutes
CELERY_TASKS_PER_WORKER = int(os.getenv("CELERY_TASKS_PER_WORKER", 1000))
CELERY_BROKER_URL = REDIS_URL
CELERY_BACKEND_URL = REDIS_URL

# Rate limiting configuration
RATE_LIMIT_DEFAULT_NORMAL = int(
    os.getenv("RATE_LIMIT_DEFAULT_NORMAL", 4)
)  # 4 per minute
RATE_LIMIT_DEFAULT_PERIOD = int(
    os.getenv("RATE_LIMIT_DEFAULT_PERIOD", 60)
)  # 60 seconds

logger = logging.getLogger(__name__)


class QueuePriority(Enum):
    """Queue priority levels"""

    URGENT = "urgent"
    NORMAL = "normal"
    LATER = "later"


class WikidataProperty:
    MapillaryPhotoID = "P1947"

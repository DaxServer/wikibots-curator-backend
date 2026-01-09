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

CELERY_CONCURRENCY = int(os.getenv("CELERY_CONCURRENCY", 2))
CELERY_MAXIMUM_WAIT_TIME = int(os.getenv("CELERY_MAXIMUM_WAIT_TIME", 60 * 4))  # minutes

REDIS_PREFIX = "skI4ZdSn18vvLkMHnPk8AEyg/8VjDRT6sY2u+BXIdsk="
REDIS_URL = os.getenv("TOOL_REDIS_URI", "redis://localhost:6379")
redis_client = redis.Redis.from_url(REDIS_URL, db=10)

logger = logging.getLogger(__name__)


class QueuePriority(Enum):
    """Queue priority levels."""

    URGENT = "urgent"
    NORMAL = "normal"
    LATER = "later"


class WikidataProperty:
    MapillaryPhotoID = "P1947"

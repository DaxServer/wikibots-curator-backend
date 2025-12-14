import logging
import os

import redis
from cashews import Cache, Command
from cashews.backends.interface import Backend
from cashews.exceptions import UnSecureDataError
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


class WikidataProperty:
    MapillaryPhotoID = "P1947"


REDIS_PREFIX = "skI4ZdSn18vvLkMHnPk8AEyg/8VjDRT6sY2u+BXIdsk="
REDIS_URL = os.getenv("TOOL_REDIS_URI", "redis://localhost:6379")
redis_client = redis.Redis.from_url(REDIS_URL, db=10)

logger = logging.getLogger(__name__)


async def integrity_middleware(call, cmd: Command, backend: Backend, *args, **kwargs):
    try:
        return await call(*args, **kwargs)
    except UnSecureDataError:
        if cmd == Command.GET:
            key = args[0] if args else kwargs.get("key")
            if key:
                logger.warning(f"[cache] Data integrity compromised for key: {key}")
                await backend.delete(key)

            # Return default to simulate cache miss
            default = kwargs.get("default")
            if default is None and len(args) > 1:
                default = args[1]
            return default
        raise


cache = Cache()
cache.setup(
    f"{REDIS_URL}/10",
    pickle_type="sqlalchemy",
    secret=TOKEN_ENCRYPTION_KEY,
    client_name=None,
)
cache.add_middleware(integrity_middleware)

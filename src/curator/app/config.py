import logging
import os
from cashews import Cache, Command
from cashews.backends.interface import Backend
from cashews.exceptions import UnSecureDataError
import redis
from pywikibot import Site
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


class WikidataEntity:
    CCBYSA40 = "Q18199165"
    Circa = "Q5727902"
    Copyrighted = "Q50423863"
    DedicatedToPublicDomainByCopyrightOwner = "Q88088423"
    FileAvailableOnInternet = "Q74228490"
    Flickr = "Q103204"
    iNaturalist = "Q16958215"
    Mapillary = "Q17985544"
    MapillaryDatabase = "Q26757498"
    Pixel = "Q355198"
    PortableAntiquitiesSchemeDatabase = "Q111225724"
    PublicDomain = "Q19652"
    StatedByCopyrightHolderAtSourceWebsite = "Q61045577"
    USACE = "Q1049334"
    WorkOfTheFederalGovernmentOfTheUnitedStates = "Q60671452"
    YouTube = "Q866"


class WikidataProperty:
    AppliesToJurisdiction = "P1001"
    AuthorNameString = "P2093"
    ContentDeliverer = "P3274"
    CoordinatesOfThePointOfView = "P1259"
    CopyrightLicense = "P275"
    CopyrightStatus = "P6216"
    Creator = "P170"
    Depicts = "P180"
    DescribedAtUrl = "P973"
    DeterminationMethod = "P459"
    FlickrPhotoId = "P12120"
    FlickrUserId = "P3267"
    Height = "P2048"
    INaturalistPhotoId = "P13419"
    INaturalistObservationId = "P5683"
    INaturalistTaxonId = "P3151"
    INaturalistUserId = "P12022"
    Inception = "P571"
    MapillaryPhotoID = "P1947"
    ORCID = "P496"
    Operator = "P137"
    PortableAntiquitiesSchemeImageID = "P13556"
    PublicationDate = "P577"
    PublishedIn = "P1433"
    StatedIn = "P248"
    SourceOfFile = "P7482"
    SourcingCircumstances = "P1480"
    Title = "P1476"
    Url = "P2699"
    Width = "P2049"
    YouTubeChannelId = "P2397"
    YouTubeHandle = "P11245"
    YouTubeVideoId = "P1651"


PWB_SITE_COMMONS = Site("commons", "commons")
PWB_SITE_WIKIDATA = Site("wikidata", "wikidata")

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
cache.setup(f"{REDIS_URL}/10", pickle_type="sqlalchemy", secret=TOKEN_ENCRYPTION_KEY)
cache.add_middleware(integrity_middleware)

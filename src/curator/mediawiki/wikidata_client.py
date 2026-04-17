"""Wikidata API client for reading and editing Wikidata items"""

import json
import logging

import requests
from authlib.integrations.requests_client import OAuth1Auth
from mwoauth import AccessToken

from curator.core.config import OAUTH_KEY, OAUTH_SECRET, USER_AGENT

logger = logging.getLogger(__name__)

WIKIDATA_API = "https://www.wikidata.org/w/api.php"


class WikidataClient:
    """Wikidata API client using OAuth1 authentication."""

    def __init__(self, access_token: AccessToken):
        auth = OAuth1Auth(
            client_id=OAUTH_KEY,
            client_secret=OAUTH_SECRET,
            token=access_token.key,
            token_secret=access_token.secret,
        )
        self._client = requests.Session()
        self._client.auth = auth
        self._client.headers.update({"User-Agent": USER_AGENT})

    def fetch_item(self, qid: str) -> dict:
        """Fetch a Wikidata item's claims and sitelinks."""
        response = self._client.get(
            WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": qid,
                "props": "claims|sitelinks",
                "format": "json",
            },
        )
        data = response.json()
        return data["entities"][qid]

    def _fetch_csrf_token(self) -> str:
        """Fetch a CSRF token from Wikidata."""
        response = self._client.get(
            WIKIDATA_API,
            params={
                "action": "query",
                "meta": "tokens",
                "format": "json",
            },
        )
        return response.json()["query"]["tokens"]["csrftoken"]

    def edit_item(
        self,
        qid: str,
        claims: list[dict] | None,
        sitelinks: dict | None,
    ) -> None:
        """Edit a Wikidata item's claims and/or sitelinks via wbeditentity."""
        token = self._fetch_csrf_token()
        payload: dict = {}
        if claims is not None:
            payload["claims"] = claims
        if sitelinks is not None:
            payload["sitelinks"] = sitelinks
        self._client.post(
            WIKIDATA_API,
            data={
                "action": "wbeditentity",
                "id": qid,
                "data": json.dumps(payload),
                "token": token,
                "format": "json",
            },
        )

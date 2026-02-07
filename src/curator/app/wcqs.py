"""
This implementation is based on video2commons: https://github.com/toolforge/video2commons/pull/262
Copyright (C) 2025  Jamie Kuppens (https://github.com/Amdrel), video2commons Contributors

video2commons is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

video2commons is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Union, cast
from urllib.parse import quote_plus

import requests
from fastapi import Request, WebSocket

from curator.app.config import USER_AGENT, WCQS_OAUTH_TOKEN, redis_client


class WcqsSession:
    """This class manages WCQS sessions and executes SPARQL queries.

    Relevant Documentation:
        https://commons.wikimedia.org/wiki/Commons:SPARQL_query_service/API_endpoint
    """

    def __init__(self, request: Union[Request, WebSocket]):
        self.session = requests.Session()
        self.request = request
        self._set_cookies()

    @property
    def _request_session(self):
        if hasattr(self.request, "session"):
            return self.request.session
        return self.request.scope.get("session", {})

    def query(self, query: str):
        """Queries the Wikimedia Commons Query Service."""
        retry_after_ts = self._check_retry()
        if retry_after_ts:
            retry_after = int(
                (retry_after_ts - datetime.now(timezone.utc)).total_seconds()
            )
            raise RuntimeError(f"Too many requests, try again in {retry_after} seconds")

        # Make the SPARQL request using the provided query.
        response = self.session.post(
            "https://commons-query.wikimedia.org/sparql",
            data=f"query={quote_plus(query)}",
            headers={
                "Accept": "application/sparql-results+json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
            },
            # Set-Cookie session refresh headers get sent with a 307 redirect.
            allow_redirects=True,
            timeout=30,
        )
        self._save_cookies()

        # Respect the rate limit status code and headers.
        #
        # https://wikitech.wikimedia.org/wiki/Robot_policy#Generally_applicable_rules
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After") or 60
            self._set_retry(int(retry_after))

            raise RuntimeError(f"Too many requests, try again in {retry_after} seconds")

        # Handle other unexpected response codes.
        content_type = response.headers.get("Content-Type")
        if (
            response.status_code < 200
            or response.status_code >= 300
            or content_type != "application/sparql-results+json;charset=utf-8"
        ):
            raise RuntimeError(
                f"Got unexpected response from SPARQL ({response.status_code}): {response.text}"
            )

        return response.json()

    def _check_retry(self):
        """Checks if we're rate limited before making SPARQL requests."""
        retry_after = redis_client.get("wcqs:retry-after")

        if retry_after:
            retry_after_str = (
                retry_after.decode("utf-8")
                if isinstance(retry_after, bytes)
                else cast(str, retry_after)
            )
            retry_after_ts = datetime.fromisoformat(retry_after_str)
            if retry_after_ts > datetime.now(timezone.utc):
                return retry_after_ts

        return None

    def _set_retry(self, retry_after: int):
        """Updates retry-after value in Redis."""
        retry_after_ts = datetime.now(timezone.utc) + timedelta(seconds=retry_after)

        redis_client.setex(
            "wcqs:retry-after",
            retry_after,
            retry_after_ts.replace(tzinfo=timezone.utc).isoformat(),
        )

    def _set_cookies(self):
        """Load authentication cookies into the session."""
        cookies = json.loads(
            self._request_session.get("wcqs_cookies", "[]")
        )
        cookie_dict = {(cookie["domain"], cookie["name"]): cookie for cookie in cookies}

        # wcqsOauth is a long lived cookie that wcqs uses to authenticate the
        # user against commons.wikimedia.org. This cookie is used to refresh
        # the wcqsSession cookie.
        wcqsOauth = cookie_dict.get(("commons-query.wikimedia.org", "wcqsOauth"))

        if wcqsOauth:
            self.session.cookies.set(
                name="wcqsOauth",
                value=wcqsOauth["value"],
                domain=wcqsOauth["domain"],
                path=wcqsOauth["path"],
                secure=wcqsOauth["secure"],
                expires=None,  # Intentional as wcqsOauth is long-lived
            )
        else:
            self.session.cookies.set(
                name="wcqsOauth",
                value=WCQS_OAUTH_TOKEN,
                domain=".commons-query.wikimedia.org",
                path="/",
                secure=True,
                expires=None,  # Intentional as wcqsOauth is long-lived
            )

        # wcqsSession is a short lived cookie (2 hour lifetime) holding a JWT
        # that grants query access to wcqs. This cookie is provided in a 307
        # redirect to any request that has a valid wcqsOauth cookie but no
        # valid wcqsSession cookie.
        wcqsSession = cookie_dict.get(("commons-query.wikimedia.org", "wcqsSession"))
        if wcqsSession:
            expires = wcqsSession["expirationDate"]
            self.session.cookies.set(
                name="wcqsSession",
                value=wcqsSession["value"],
                domain=wcqsSession["domain"],
                path=wcqsSession["path"],
                secure=wcqsSession["secure"],
                expires=int(expires) if expires else None,
            )

    def _save_cookies(self):
        """Save cookies from the session to Redis."""
        cookies = [
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "expirationDate": cookie.expires,
                "secure": cookie.secure,
            }
            for cookie in self.session.cookies
        ]

        self._request_session["wcqs_cookies"] = json.dumps(cookies)

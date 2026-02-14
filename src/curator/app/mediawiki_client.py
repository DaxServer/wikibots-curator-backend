"""
MediaWiki API client
"""

import hashlib
import json
import logging
import secrets
from dataclasses import dataclass
from typing import Any

import jwt
import requests
from authlib.integrations.requests_client import OAuth1Auth
from jwt.exceptions import PyJWTError
from mwoauth import AccessToken

from curator.app.config import OAUTH_KEY, OAUTH_SECRET, USER_AGENT
from curator.asyncapi import ErrorLink

logger = logging.getLogger(__name__)

# Wikimedia Commons API endpoints
# Note: Must use non-nice URL format for OAuth requests
# See: https://phabricator.wikimedia.org/T59500
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_OAUTH_IDENTIFY = (
    "https://commons.wikimedia.org/w/index.php?title=Special:OAuth/identify"
)


@dataclass
class UploadResult:
    """Result of a file upload operation"""

    success: bool
    title: str | None = None
    url: str | None = None
    error: str | None = None


class MediaWikiClient:
    """
    MediaWiki API client using OAuth1 authentication.
    """

    def __init__(
        self,
        access_token: AccessToken,
    ):
        self.access_token = access_token

        auth = OAuth1Auth(
            client_id=OAUTH_KEY,
            client_secret=OAUTH_SECRET,
            token=access_token.key,
            token_secret=access_token.secret,
        )

        self._client = requests.Session()
        self._client.auth = auth
        self._client.headers.update({"User-Agent": USER_AGENT})
        self._groups: set[str] | None = None

    def _api_request(
        self,
        params: dict[str, Any],
        method: str = "GET",
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        """
        Make a request to the MediaWiki API.
        """
        # Format is added to params for GET requests
        if "format" not in params:
            params["format"] = "json"

        try:
            response = self._client.request(
                method,
                COMMONS_API,
                params=params,
                data=data,
                files=files,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise

    def get_user_groups(self) -> set[str]:
        """
        Get user groups via OAuth /identify endpoint.
        """
        if self._groups is not None:
            return self._groups

        nonce = secrets.token_hex(16)

        # Make signed request to identify endpoint
        try:
            response = self._client.get(
                COMMONS_OAUTH_IDENTIFY,
                headers={"X-OAuth-Nonce": nonce},
                timeout=300.0,
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch user groups: {e}")
            raise

        # Decode JWT (MediaWiki returns base64url-encoded JWT)
        jwt_body = response.text

        try:
            claims = jwt.decode(
                jwt_body,
                key=OAUTH_SECRET,
                algorithms=["HS256"],
                audience=OAUTH_KEY,
            )
        except PyJWTError as e:
            logger.error(f"JWT validation failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error while decoding JWT: {e}")
            raise

        groups = set(claims.get("groups", []))
        logger.info(f"User groups: {groups}")
        self._groups = groups
        return groups

    def is_privileged(self) -> bool:
        """
        Check if user has privileged groups (patroller, sysop).
        """
        return bool(self.get_user_groups() & {"patroller", "sysop"})

    def get_csrf_token(self) -> str:
        """
        Get CSRF token for edit operations.
        """
        params = {
            "action": "query",
            "meta": "tokens",
            "type": "csrf",
        }

        data = self._api_request(params)
        csrf_token = data["query"]["tokens"]["csrftoken"]
        logger.debug(f"Got CSRF token: {csrf_token[:10]}...")
        return csrf_token

    def check_title_blacklisted(self, filename: str) -> tuple[bool, str]:
        """
        Check if a filename is blacklisted.
        """
        params = {
            "action": "titleblacklist",
            "tbaction": "create",
            "tbtitle": f"File:{filename}",
        }

        try:
            data = self._api_request(params)

            if (
                "titleblacklist" in data
                and data["titleblacklist"].get("result") == "blacklisted"
            ):
                reason = data["titleblacklist"].get("reason", "Title is blacklisted")
                return True, reason

            return False, ""

        except Exception as e:
            logger.warning(f"Failed to check title blacklist for {filename}: {e}")
            return False, ""

    def find_duplicates(self, sha1: str) -> list[ErrorLink]:
        """
        Find existing files with same SHA1 hash.

        Returns list of ErrorLink objects with title and url.
        """
        params = {
            "action": "query",
            "list": "allimages",
            "aisha1": sha1,
        }

        data = self._api_request(params)

        duplicates = [
            ErrorLink(title=img["title"], url=img["descriptionurl"])
            for img in data.get("query", {}).get("allimages", [])
        ]
        logger.info(f"Found {len(duplicates)} duplicates for SHA1 {sha1}")
        return duplicates

    def upload_file(
        self,
        filename: str,
        file_content: bytes,
        wikitext: str,
        edit_summary: str,
        chunk_size: int = 1024 * 1024 * 1,  # 1MB chunks
    ) -> UploadResult:
        """
        Upload a file to Commons using chunked upload.
        """
        # Check for duplicates first
        sha1 = hashlib.sha1(file_content).hexdigest()
        duplicates = self.find_duplicates(sha1)
        if duplicates:
            return UploadResult(
                success=False,
                error=f"File already exists: {duplicates[0].title}",
            )

        # Get CSRF token
        csrf_token = self.get_csrf_token()

        file_size = len(file_content)
        total_chunks = (file_size + chunk_size - 1) // chunk_size

        logger.info(
            f"Uploading {filename} ({file_size} bytes) in {total_chunks} chunks"
        )

        # Chunked upload
        file_key = None
        for chunk_num in range(total_chunks):
            offset = chunk_num * chunk_size
            chunk = file_content[offset : offset + chunk_size]

            params = {
                "action": "upload",
                "filename": filename,
                "comment": edit_summary,
                "text": wikitext,
                "token": csrf_token,
                "offset": str(offset),
                "filesize": str(file_size),
                "stash": "1" if chunk_num < total_chunks - 1 else "0",
            }

            # Add filekey if we have one (for chunks 2+)
            if file_key:
                params["filekey"] = file_key

            files = {"file": ("chunk", chunk, "application/octet-stream")}

            data = self._api_request(params, method="POST", files=files, timeout=60.0)

            if "error" in data:
                return UploadResult(
                    success=False,
                    error=data["error"].get("info", "Upload failed"),
                )

            # For stashed chunks, we get a file key
            if "upload" in data:
                file_key = data["upload"].get("filekey")

            logger.debug(f"Uploaded chunk {chunk_num + 1}/{total_chunks}")

        # Get the final result
        if "upload" in data:
            result = data["upload"]
            if result.get("result") == "Success":
                title = result.get("filename", result.get("title"))
                image_url = result.get("imageurl")
                return UploadResult(
                    success=True,
                    title=title,
                    url=image_url,
                )

        return UploadResult(success=False, error="Upload failed: unknown reason")

    def apply_sdc(
        self,
        filename: str,
        sdc: list[dict] | None = None,
        labels: list[dict] | None = None,
        edit_summary: str = "",
    ) -> bool:
        """
        Apply Structured Data Commons to a file.
        """
        if not sdc and not labels:
            return False

        # Get CSRF token
        csrf_token = self.get_csrf_token()

        # Build wbeditentity payload
        payload_data: dict[str, Any] = {}
        if sdc:
            payload_data["claims"] = sdc
        if labels:
            # labels is already in correct format: {"language_code": "label text"}
            payload_data["labels"] = labels

        # Separate query params from POST data
        # MediaWiki API requires action, site, title in query params
        # and data, token, summary, bot in POST body
        query_params = {
            "action": "wbeditentity",
            "site": "commonswiki",
            "title": f"File:{filename}",
            "format": "json",
        }

        post_data = {
            "data": json.dumps(payload_data),
            "token": csrf_token,
            "summary": edit_summary,
            "bot": "0",  # False as string "0" or just omit/use "0"
        }

        # Make POST request with data in body
        response_data = self._api_request(
            query_params,
            method="POST",
            data=post_data,
            timeout=60.0,
        )

        # Check for API errors in response
        if "error" in response_data:
            error_code = response_data["error"].get("code", "unknown")
            error_info = response_data["error"].get("info", "Unknown error")
            logger.error(
                f"SDC apply failed for {filename}: {error_code} - {error_info}"
            )
            raise Exception(f"SDC apply failed: {error_code} - {error_info}")

        logger.info(f"SDC applied to {filename}")
        return True

    def fetch_sdc(self, media_id: str) -> tuple[dict | None, dict | None]:
        """
        Fetch SDC and labels from Commons.
        """
        params = {
            "action": "wbgetentities",
            "ids": media_id,
            "props": "claims|labels",
        }

        data = self._api_request(params)

        # Check for error response (file does not exist)
        if "error" in data:
            error_info = data["error"].get("info", "Unknown error")
            raise Exception(f"Could not find an entity: {error_info}")

        # Check if media ID exists in response
        if media_id not in data.get("entities", {}):
            logger.warning(f"Media ID {media_id} not found on Commons")
            return None, None

        entity = data["entities"][media_id]

        # Check if file exists but SDC is not created (has "missing" key)
        if "missing" in entity:
            logger.info(f"File {media_id} exists but SDC not created yet")
            return None, None

        # Extract statements (API returns 'statements' key)
        sdc = entity.get("statements")
        labels = entity.get("labels")

        return sdc, labels

    def upload_file_with_sdc(
        self,
        filename: str,
        file_content: bytes,
        wikitext: str,
        edit_summary: str,
        sdc: list[dict] | None = None,
        labels: list[dict] | None = None,
    ) -> UploadResult:
        """
        Complete upload workflow: check blacklist, upload, apply SDC.
        """
        # Check title blacklist
        blacklisted, reason = self.check_title_blacklisted(filename)
        if blacklisted:
            return UploadResult(
                success=False,
                error=f"Title blacklisted: {reason}",
            )

        # Upload file
        result = self.upload_file(filename, file_content, wikitext, edit_summary)
        if not result.success or not result.title:
            return result

        # Apply SDC
        try:
            self.apply_sdc(result.title, sdc, labels, edit_summary)
        except Exception as e:
            logger.warning(f"Failed to apply SDC: {e}")

        return result


def create_mediawiki_client(access_token: AccessToken) -> MediaWikiClient:
    """
    Create a MediaWiki API client with OAuth1 authentication.
    """
    return MediaWikiClient(access_token=access_token)

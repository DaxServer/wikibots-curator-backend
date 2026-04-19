"""
MediaWiki API client
"""

import json
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any

import jwt
import requests
from authlib.integrations.requests_client import OAuth1Auth
from jwt.exceptions import PyJWTError
from mwoauth import AccessToken

from curator.asyncapi import ErrorLink
from curator.core.config import HTTP_RETRY_DELAYS, OAUTH_KEY, OAUTH_SECRET, USER_AGENT
from curator.core.errors import DuplicateUploadError

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
        csrf: bool = False,
    ) -> dict[str, Any]:
        """
        Make a request to the MediaWiki API with retry logic.
        """
        if "format" not in params:
            params["format"] = "json"

        backoffs = [0, 1, 3]

        attempt = 0
        while attempt < len(backoffs):
            backoff = backoffs[attempt]
            if attempt > 0 and backoff > 0:
                time.sleep(backoff)

            if csrf:
                data = data or {}
                data["token"] = self.get_csrf_token()

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
                result = response.json()

                if csrf and result.get("error", {}).get("code") == "badtoken":
                    if attempt < len(backoffs) - 1:
                        logger.warning(
                            f"Invalid CSRF token (attempt {attempt + 1}), retrying with fresh token"
                        )
                        attempt += 1
                        continue

                if (
                    result.get("error", {}).get("code")
                    == "mwoauth-invalid-authorization"
                    and "Nonce already used" in result["error"].get("info", "")
                    and attempt < len(backoffs) - 1
                ):
                    logger.warning(
                        f"Nonce already used (attempt {attempt + 1}), retrying"
                    )
                    attempt += 1
                    continue

                return result
            except requests.exceptions.RequestException as e:
                if attempt == len(backoffs) - 1:
                    logger.error(f"API request failed: {e}")
                    raise
                logger.warning(
                    f"API request failed (attempt {attempt + 1}), retrying in {backoffs[attempt + 1]}s"
                )

            attempt += 1

        raise AssertionError("Unreachable")

    def get_user_groups(self) -> set[str]:
        """
        Get user groups via OAuth /identify endpoint.
        """
        if self._groups is not None:
            return self._groups

        nonce = secrets.token_hex(16)

        try:
            response = self._client.get(
                COMMONS_OAUTH_IDENTIFY,
                headers={"X-OAuth-Nonce": nonce},
                timeout=300.0,
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(e)
            raise

        jwt_body = response.text

        try:
            claims = jwt.decode(
                jwt_body,
                key=OAUTH_SECRET,
                algorithms=["HS256"],
                audience=OAUTH_KEY,
            )
        except PyJWTError as e:
            logger.error(e)
            raise
        except Exception as e:
            logger.error(e)
            raise

        groups = set(claims.get("groups", []))
        logger.info(f"User groups: {groups}")
        self._groups = groups
        return groups

    def get_user_rate_limits(self) -> tuple[dict[str, dict], list[str]]:
        """Fetch user rate limits and rights from the MediaWiki userinfo API."""
        params: dict[str, str] = {
            "action": "query",
            "meta": "userinfo",
            "uiprop": "ratelimits|rights",
        }
        data = self._api_request(params)
        userinfo = data["query"]["userinfo"]
        return userinfo["ratelimits"], userinfo.get("rights", [])

    def get_csrf_token(self) -> str:
        """
        Get CSRF token for edit operations.
        """
        params: dict[str, str] = {
            "action": "query",
            "meta": "tokens",
            "type": "csrf",
        }

        data = self._api_request(params)
        csrf_token = data["query"]["tokens"]["csrftoken"]
        logger.info(f"Got CSRF token: {csrf_token[:10]}...")
        return csrf_token

    def check_title_blacklisted(self, filename: str) -> tuple[bool, str]:
        """
        Check if a filename is blacklisted.
        """
        params: dict[str, str] = {
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
            logger.error(f"Error checking title blacklist: {e}")
            return False, ""

    def find_duplicates(self, sha1: str) -> list[ErrorLink]:
        """
        Find existing files with same SHA1 hash.

        Returns list of ErrorLink objects with title and url.
        """
        params: dict[str, str] = {
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

    def get_file_sha1(self, title: str) -> str | None:
        """Return the SHA1 hash of an existing file on Commons, or None if not found."""
        params: dict[str, str] = {
            "action": "query",
            "formatversion": "2",
            "titles": title if title.startswith("File:") else f"File:{title}",
            "prop": "imageinfo",
            "iiprop": "sha1",
        }
        data = self._api_request(params)
        pages = data.get("query", {}).get("pages", [])
        if pages and pages[0].get("imageinfo"):
            sha1 = pages[0]["imageinfo"][0].get("sha1")
            logger.info(f"SHA1 for {title}: {sha1}")
            return sha1
        logger.info(f"No imageinfo found for {title}")
        return None

    def _upload_chunk(
        self,
        chunk_num: int,
        total_chunks: int,
        query_params: dict[str, str],
        post_data: dict[str, str],
        files: dict[str, Any],
        file_sha1: str | None = None,
    ) -> str | None | UploadResult:
        """Upload a single chunk with retry logic, return file_key or UploadResult on error."""
        max_attempts = len(HTTP_RETRY_DELAYS) + 1
        for chunk_attempt in range(max_attempts):
            is_last_attempt = chunk_attempt == max_attempts - 1
            delay = HTTP_RETRY_DELAYS[chunk_attempt] if not is_last_attempt else 0

            try:
                data = self._api_request(
                    query_params,
                    method="POST",
                    data=post_data,
                    files=files,
                    timeout=60.0,
                    csrf=True,
                )
            except requests.exceptions.RequestException as e:
                if is_last_attempt:
                    logger.error(
                        f"Failed to upload chunk {chunk_num + 1}/{total_chunks} "
                        f"after {max_attempts} attempts: {e}"
                    )
                    return UploadResult(
                        success=False,
                        error=f"Chunk {chunk_num + 1}/{total_chunks} failed after {max_attempts} attempts: {e}",
                    )
                logger.warning(
                    f"Chunk {chunk_num + 1}/{total_chunks} upload failed "
                    f"(attempt {chunk_attempt + 1}/{max_attempts}), "
                    f"retrying in {delay} seconds: {e}"
                )
                time.sleep(delay)
                continue

            if "error" in data:
                error_code = data["error"].get("code", "")
                error_info = data["error"].get("info", "Upload failed")
                if not is_last_attempt and (
                    "UploadStashFileException" in error_code
                    or "uploadstash-exception" in error_code
                    or "UploadChunkFileException" in error_code
                    or "JobQueueError" in error_code
                    or "backend-fail-internal" in error_info
                    or "internal_api_error_" in error_code
                ):
                    logger.warning(
                        f"Chunk {chunk_num + 1}/{total_chunks} stash error "
                        f"(attempt {chunk_attempt + 1}/{max_attempts}), "
                        f"retrying in {delay} seconds: {data}"
                    )
                    time.sleep(delay)
                    continue
                logger.error(data)
                return UploadResult(success=False, error=f"{error_code}: {error_info}")

            if "upload" in data:
                result = data["upload"]
                # IMPORTANT: Duplicate warnings appear here on final chunk (with stash=1)
                # We must raise BEFORE final commit to avoid publishing duplicates
                warnings = result.get("warnings", {})
                if "duplicate" in warnings:
                    dup_titles = warnings["duplicate"]
                    duplicates = [
                        ErrorLink(
                            title=d,
                            url=f"https://commons.wikimedia.org/wiki/File:{d.replace(' ', '_')}",
                        )
                        for d in dup_titles
                    ]
                    raise DuplicateUploadError(
                        duplicates, f"File already exists as {dup_titles}"
                    )
                if "exists" in warnings and file_sha1:
                    existing_title = warnings["exists"]
                    logger.info(
                        f"File exists warning for {existing_title}, checking SHA1"
                    )
                    remote_sha1 = self.get_file_sha1(existing_title)
                    if remote_sha1 == file_sha1:
                        logger.info(
                            f"SHA1 match confirmed, treating as duplicate: {existing_title}"
                        )
                        raise DuplicateUploadError(
                            [
                                ErrorLink(
                                    title=existing_title,
                                    url=f"https://commons.wikimedia.org/wiki/File:{existing_title.replace(' ', '_')}",
                                )
                            ],
                            f"File already exists as {existing_title}",
                        )
                    return UploadResult(
                        success=False,
                        error=f"File already exists with different content: {existing_title}",
                    )

                if warnings:
                    logger.warning(warnings)
                    return UploadResult(
                        success=False,
                        error=f"Upload warnings: {warnings}",
                    )

                # result: "Success" with stash=1 means chunks stashed successfully;
                # the file is NOT published yet - final commit is still required
                return result.get("filekey")

        raise AssertionError("Unreachable")

    def upload_file(
        self,
        filename: str,
        file_path: str,
        wikitext: str,
        edit_summary: str,
        chunk_size: int = 1024 * 1024 * 1,  # 1MB chunks
        file_sha1: str | None = None,
    ) -> UploadResult:
        """Upload a file to Commons using chunked upload."""
        file_size = os.path.getsize(file_path)
        total_chunks = (file_size + chunk_size - 1) // chunk_size

        logger.info(
            f"Uploading {filename} ({file_size} bytes) in {total_chunks} chunks"
        )

        file_key = None
        with open(file_path, "rb") as f:
            for chunk_num in range(total_chunks):
                offset = chunk_num * chunk_size
                f.seek(offset)
                chunk = f.read(chunk_size)

                query_params: dict[str, str] = {
                    "action": "upload",
                    "format": "json",
                }

                post_data: dict[str, str] = {
                    "filename": filename,
                    "comment": edit_summary,
                    "text": wikitext,
                    "offset": str(offset),
                    "filesize": str(file_size),
                    "stash": "1",
                }

                if file_key:
                    post_data["filekey"] = file_key

                files = {
                    "chunk": (f"{chunk_num}.jpg", chunk, "application/octet-stream")
                }

                chunk_result = self._upload_chunk(
                    chunk_num, total_chunks, query_params, post_data, files, file_sha1
                )
                if isinstance(chunk_result, UploadResult):
                    if (
                        file_key
                        and chunk_result.error
                        and "stashfailed" in chunk_result.error
                        and "already completed" in chunk_result.error
                    ):
                        logger.info(
                            f"Chunk {chunk_num + 1}/{total_chunks} already stashed (stash complete), proceeding to final commit"
                        )
                        break
                    return chunk_result
                file_key = chunk_result

                logger.info(
                    f"Uploaded chunk {chunk_num + 1}/{total_chunks} filekey: {file_key}"
                )

        if file_key:
            query_params = {
                "action": "upload",
                "format": "json",
            }

            post_data = {
                "filename": filename,
                "comment": edit_summary,
                "text": wikitext,
                "filekey": file_key,
            }

            max_attempts = len(HTTP_RETRY_DELAYS) + 1
            for commit_attempt in range(max_attempts):
                is_last_attempt = commit_attempt == max_attempts - 1
                delay = HTTP_RETRY_DELAYS[commit_attempt] if not is_last_attempt else 0

                try:
                    data = self._api_request(
                        query_params,
                        method="POST",
                        data=post_data,
                        timeout=60.0,
                        csrf=True,
                    )
                except requests.exceptions.RequestException as e:
                    if is_last_attempt:
                        logger.error(
                            f"Final commit failed after {max_attempts} attempts: {e}"
                        )
                        return UploadResult(
                            success=False, error=f"Final commit failed: {e}"
                        )
                    logger.warning(
                        f"Final commit network error (attempt {commit_attempt + 1}/{max_attempts}), "
                        f"retrying in {delay} seconds: {e}"
                    )
                    time.sleep(delay)
                    continue

                if "error" in data:
                    error_code = data["error"].get("code", "")
                    error_info = data["error"].get(
                        "info", "Upload failed while committing chunked uploads"
                    )
                    if not is_last_attempt and (
                        "backend-fail-internal" in error_code
                        or "JobQueueError" in error_code
                        or "internal_api_error_" in error_code
                    ):
                        logger.warning(
                            f"Final commit backend error (attempt {commit_attempt + 1}/{max_attempts}), "
                            f"retrying in {delay} seconds: {data}"
                        )
                        time.sleep(delay)
                        continue
                    logger.error(data)
                    return UploadResult(
                        success=False,
                        error=f"{error_code}: {error_info}",
                    )

                logger.info(f"Final commit for {filename} with filekey {file_key}")

                if "upload" in data:
                    result = data["upload"]
                    warnings = result.get("warnings", {})
                    if "nochange" in warnings:
                        existing_title = warnings.get("exists", filename)
                        raise DuplicateUploadError(
                            [
                                ErrorLink(
                                    title=existing_title,
                                    url=f"https://commons.wikimedia.org/wiki/File:{existing_title.replace(' ', '_')}",
                                )
                            ],
                            f"File already exists as {existing_title}",
                        )
                    if result.get("result") == "Success":
                        title = result.get("filename", result.get("title"))
                        imageinfo = result.get("imageinfo", {})
                        image_url = imageinfo.get("descriptionurl")
                        return UploadResult(
                            success=True,
                            title=title,
                            url=image_url,
                        )

                logger.error(data)
                return UploadResult(
                    success=False, error="Upload failed: unknown reason"
                )

        raise AssertionError("Unreachable")

    def _fetch_page(self, filename: str) -> dict:
        """
        Fetch page data from Commons API.
        """
        query_params = {
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "rvlimit": 1,
            "rvslots": "*",
            "titles": f"File:{filename}",
            "formatversion": "2",
        }

        max_attempts = len(HTTP_RETRY_DELAYS) + 1
        for attempt in range(max_attempts):
            is_last_attempt = attempt == max_attempts - 1
            delay = HTTP_RETRY_DELAYS[attempt] if not is_last_attempt else 0
            result = self._api_request(query_params)
            if "query" in result:
                return result["query"]["pages"][0]
            if is_last_attempt:
                logger.error(
                    f"Unexpected API response for {filename} after {max_attempts} attempts: {result}"
                )
                raise KeyError(f"'query' key missing in API response for {filename}")
            logger.warning(
                f"Unexpected API response for {filename} "
                f"(attempt {attempt + 1}/{max_attempts}), retrying in {delay}s: {result}"
            )
            time.sleep(delay)

        raise AssertionError("Unreachable")

    def file_exists(self, filename: str) -> bool:
        """
        Check if a file exists on Commons.
        """
        page = self._fetch_page(filename)
        return "missing" not in page

    def null_edit(self, filename: str) -> bool:
        """
        Perform a null edit on a file page to trigger template re-parsing.
        """
        page = self._fetch_page(filename)
        if "missing" in page:
            logger.warning(f"File {filename} does not exist, skipping null edit")
            return False

        edit_params = {
            "action": "edit",
            "title": f"File:{filename}",
            "format": "json",
        }

        edit_data = {
            "text": page["revisions"][0]["slots"]["main"]["content"],
            "summary": "null edit",
            "bot": "0",
        }

        response_data = self._api_request(
            edit_params, method="POST", data=edit_data, timeout=60.0, csrf=True
        )

        if "error" in response_data:
            error_code = response_data["error"].get("code", "unknown")
            error_info = response_data["error"].get("info", "Unknown error")
            logger.error(response_data)
            raise ValueError(f"Null edit failed: {error_code} - {error_info}")

        logger.info(f"Null edit performed on {filename}")
        return True

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

        payload_data: dict[str, Any] = {}
        if sdc:
            payload_data["claims"] = sdc
        if labels:
            payload_data["labels"] = labels

        query_params: dict[str, str] = {
            "action": "wbeditentity",
            "site": "commonswiki",
            "title": f"File:{filename}",
            "format": "json",
        }

        post_data: dict[str, str] = {
            "data": json.dumps(payload_data),
            "summary": edit_summary,
            "bot": "0",
        }

        response_data = self._api_request(
            query_params,
            method="POST",
            data=post_data,
            timeout=60.0,
            csrf=True,
        )

        if "error" in response_data:
            error_code = response_data["error"].get("code", "unknown")
            error_info = response_data["error"].get("info", "Unknown error")
            logger.error(response_data)
            raise ValueError(f"SDC apply failed: {error_code} - {error_info}")

        logger.info(f"SDC applied to {filename}")

        self.null_edit(filename)

        return True

    def is_category_deleted(self, title: str) -> bool:
        """Return True if the category has a deletion log entry on Commons."""
        result = self._api_request(
            {
                "action": "query",
                "list": "logevents",
                "letype": "delete",
                "letitle": f"Category:{title}",
                "formatversion": "2",
            }
        )
        return len(result.get("query", {}).get("logevents", [])) > 0

    def create_page(self, title: str, text: str) -> str:
        """Create a wiki page, returning the created page title."""
        query_params: dict[str, str] = {
            "action": "edit",
            "format": "json",
            "formatversion": "2",
        }
        post_data: dict[str, str] = {"title": title, "text": text, "createonly": "1"}
        result = self._api_request(
            query_params, method="POST", data=post_data, csrf=True
        )

        if "error" in result:
            if result["error"].get("code") == "articleexists":
                return title
            logger.error(result)
            raise ValueError(result["error"].get("info", "Edit failed"))
        return result["edit"]["title"]

    def get_category_members(self, category: str) -> list[str]:
        """Return all file titles in the given category."""
        params: dict[str, str] = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmtype": "file",
            "cmlimit": "500",
        }
        titles: list[str] = []
        while True:
            result = self._api_request(params)
            members = result.get("query", {}).get("categorymembers", [])
            titles.extend(m["title"] for m in members)
            if "continue" not in result:
                break
            params = {**params, "cmcontinue": result["continue"]["cmcontinue"]}
        logger.info(
            f"Retrieved {len(titles)} file titles in [[Category:{category.replace('_', ' ')}]]"
        )
        return titles

    def replace_category_in_page(self, title: str, source: str, target: str) -> bool:
        """Replace source category with target in a page's wikitext. Returns True if replaced."""
        result = self._api_request(
            {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": title,
            }
        )
        pages = result.get("query", {}).get("pages", {})
        page = next(iter(pages.values()))
        wikitext = (
            page.get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("*", "")
        )
        source_normalized = source.replace("_", " ")
        pattern = re.compile(
            r"\[\[Category:" + re.escape(source_normalized) + r"(\|[^\]]+)?\]\]"
        )
        if not pattern.search(wikitext):
            return False
        new_text = pattern.sub(
            lambda m: f"[[Category:{target}{m.group(1) or ''}]]",
            wikitext,
        )
        self._api_request(
            {"action": "edit", "format": "json", "formatversion": "2"},
            method="POST",
            data={
                "title": title,
                "text": new_text,
                "summary": f"Recategorize: [[Category:{source_normalized}]] → [[Category:{target}]]",
            },
            csrf=True,
        )
        logger.info(
            f"Recategorized {title} from [[Category:{source_normalized}]] to [[Category:{target}]]"
        )
        return True

    def fetch_sdc(self, title: str) -> tuple[dict | None, dict | None]:
        """
        Fetch SDC and labels from Commons by file title.
        """
        api_title = title if title.startswith("File:") else f"File:{title}"

        params: dict[str, str] = {
            "action": "wbgetentities",
            "sites": "commonswiki",
            "titles": api_title,
            "props": "claims|labels",
        }

        data = self._api_request(params)

        if "error" in data:
            error_info = data["error"].get("info", "Unknown error")
            logger.error(data)
            raise ValueError(f"Could not find an entity: {error_info}")

        entities = data.get("entities", {})
        if not entities:
            logger.warning(f"Title {title} not found on Commons")
            return None, None

        entity_id = next(iter(entities))
        entity = entities[entity_id]

        # entity ID "-1" means non-existent file when using sites/titles lookup
        if entity_id == "-1":
            logger.warning(f"File {title} does not exist on Commons")
            raise ValueError(f"File {title} does not exist on Commons")

        # positive entity ID with "missing" key means file exists but has no SDC
        if "missing" in entity:
            logger.info(f"File {title} exists but SDC not created yet")
            return None, None

        sdc = entity.get("statements")
        labels = entity.get("labels")

        return sdc, labels

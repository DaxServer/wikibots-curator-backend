import asyncio
import hashlib
import logging
import time
from tempfile import NamedTemporaryFile
from typing import Any, Optional

import httpx
from mwoauth import AccessToken

from curator.app.config import OAUTH_KEY, OAUTH_SECRET
from curator.app.mediawiki_client import MediaWikiClient
from curator.app.thread_utils import ThreadLocalDict
from curator.asyncapi import ErrorLink, Label, Statement

logger = logging.getLogger(__name__)

# Maximum number of retries for Mapillary image download errors
MAX_DOWNLOAD_RETRIES = 2


pywikibot: Any | None = None
config: Any | None = None


def _ensure_pywikibot() -> None:
    global pywikibot, config
    if pywikibot is None or config is None:
        import pywikibot as _pywikibot
        import pywikibot.config as _config

        if pywikibot is None:
            pywikibot = _pywikibot
        if config is None:
            config = _config

        # PATCH: Make config.authenticate thread-local to prevent race conditions
        # in multi-threaded environment. pywikibot reads this global dict
        # on every request.
        if not isinstance(config.authenticate, ThreadLocalDict):
            config.authenticate = ThreadLocalDict(config.authenticate)  # type: ignore

        # Set put_throttle once globally during initialization
        config.put_throttle = 0  # type: ignore


class DuplicateUploadError(Exception):
    def __init__(self, duplicates: list[ErrorLink], message: str):
        super().__init__(message)
        self.duplicates = duplicates


class IsolatedSite:
    """
    A wrapper around pywikibot.Site that ensures thread-safe execution
    by setting up the thread-local configuration before every operation.
    """

    def __init__(self, access_token: AccessToken, username: str):
        self.access_token = access_token
        self.username = username
        self._site = None

    def _setup_context(self):
        """Sets up the thread-local pywikibot configuration."""
        _ensure_pywikibot()
        assert config

        config.authenticate["commons.wikimedia.org"] = (
            OAUTH_KEY,
            OAUTH_SECRET,
        ) + tuple(self.access_token)

    def _get_or_create_site(self):
        """Creates or retrieves the cached Site object."""
        # Must be called inside the context where config is set
        assert pywikibot
        if not self._site:
            self._site = pywikibot.Site("commons", "commons", user=self.username)
            self._site.login()
        return self._site

    def run_sync(self, func, *args, **kwargs):
        """Run a function synchronously with the correct site context."""
        self._setup_context()
        site = self._get_or_create_site()
        return func(site, *args, **kwargs)

    async def run(self, func, *args, **kwargs):
        """Run a function in a separate thread with correct site context."""
        return await asyncio.to_thread(self.run_sync, func, *args, **kwargs)


def create_isolated_site(access_token: AccessToken, username: str) -> IsolatedSite:
    """
    Create an IsolatedSite wrapper.
    """
    return IsolatedSite(access_token, username)


def upload_file_chunked(
    file_name: str,
    file_url: str,
    wikitext: str,
    edit_summary: str,
    upload_id: int,
    batch_id: int,
    mediawiki_client: MediaWikiClient,
    sdc: Optional[list[Statement]] = None,
    labels: Optional[Label] = None,
) -> dict:
    """
    Upload a file to Commons using MediaWikiClient's upload_file method.

    - Uses chunked uploads
    - Streams download to temp file for memory efficiency
    - Returns a dict payload {"result": "success", "title": ..., "url": ...}.
    """
    with NamedTemporaryFile() as temp_file:
        # Download directly to temp file, get hash
        file_hash = download_file(file_url, temp_file, upload_id, batch_id)
        logger.info(f"[{upload_id}/{batch_id}] file hash: {file_hash}")

        # Check for duplicates before upload using hash
        duplicates_list = mediawiki_client.find_duplicates(file_hash)
        if len(duplicates_list) > 0:
            raise DuplicateUploadError(
                duplicates_list,
                f"File {file_name} already exists on Commons",
            )

        # Upload using temp file path
        upload_result = mediawiki_client.upload_file(
            filename=file_name,
            file_path=temp_file.name,
            wikitext=wikitext,
            edit_summary=edit_summary,
        )

        # Check for upload errors
        if not upload_result.success:
            raise ValueError(upload_result.error or "Upload failed")

        # Apply SDC after successful upload
        apply_sdc(file_name, mediawiki_client, sdc, edit_summary, labels)

        return {
            "result": "success",
            "title": upload_result.title,
            "url": upload_result.url,
        }


def download_file(
    file_url: str, temp_file, upload_id: int = 0, batch_id: int = 0
) -> str:
    """
    Download file directly to temp file using streaming.
    Returns SHA1 hash computed during download.
    """
    for attempt in range(MAX_DOWNLOAD_RETRIES):
        try:
            with httpx.stream("GET", file_url, timeout=60) as resp:
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "")
                if "application/x-php" in content_type:
                    # Got application/x-php instead of image
                    if attempt < MAX_DOWNLOAD_RETRIES - 1:
                        logger.warning(
                            f"[{upload_id}/{batch_id}] Received application/x-php instead of image, "
                            f"retrying in 2 seconds... (attempt {attempt + 1}/{MAX_DOWNLOAD_RETRIES})"
                        )
                        time.sleep(2)
                        continue
                    else:
                        raise ValueError(
                            f"Failed to download image from {file_url}: received application/x-php content type after {MAX_DOWNLOAD_RETRIES} retries"
                        )

                # Stream download: write chunks to temp file and update hash
                sha1 = hashlib.sha1()
                for chunk in resp.iter_bytes(chunk_size=8192):
                    temp_file.write(chunk)
                    sha1.update(chunk)

                return sha1.hexdigest()
        except httpx.HTTPError:
            if attempt < MAX_DOWNLOAD_RETRIES - 1:
                continue
            raise


def ensure_uploaded(
    mediawiki_client: MediaWikiClient,
    uploaded: bool,
    file_name: str,
):
    exists = mediawiki_client.file_exists(file_name)
    if not uploaded and exists:
        raise ValueError(f"File {file_name} already exists on Commons")

    if not exists:
        raise ValueError("File upload failed")


def _build_sdc_payload(
    sdc: Optional[list[Statement]], labels: Optional[Label]
) -> dict[str, Any]:
    """
    Build the wbeditentity data payload from SDC statements and labels
    """
    data: dict[str, Any] = {}

    if sdc:
        data["claims"] = []
        for s in sdc:
            if not isinstance(s, Statement):
                s = Statement.model_validate(s)
            data["claims"].append(
                s.model_dump(mode="json", by_alias=True, exclude_none=True)
            )

    if labels:
        if not isinstance(labels, Label):
            labels = Label.model_validate(labels)
        data["labels"] = [
            labels.model_dump(mode="json", by_alias=True, exclude_none=True)
        ]

    return data


def apply_sdc(
    file_title: str,
    mediawiki_client: MediaWikiClient,
    sdc: Optional[list[Statement]] = None,
    edit_summary: str = "",
    labels: Optional[Label] = None,
) -> bool:
    """
    Apply SDC to an existing file on Commons using MediaWikiClient
    """
    data = _build_sdc_payload(sdc, labels)

    if not data:
        return False

    # Strip "File:" prefix if present
    filename = file_title
    if filename.startswith("File:"):
        filename = filename[5:]

    return mediawiki_client.apply_sdc(
        filename=filename,
        sdc=data.get("claims"),
        labels=data.get("labels"),
        edit_summary=edit_summary,
    )


def fetch_sdc_from_api(
    title: str, mediawiki_client: MediaWikiClient
) -> tuple[list[Statement] | None, dict[str, Label] | None]:
    """
    Fetch SDC data and labels.
    """
    # Use MediaWikiClient to fetch raw data
    sdc, labels = mediawiki_client.fetch_sdc(title)

    if sdc is None:
        return None, None

    # Convert raw dicts to Statement and Label models
    existing_sdc = []
    for prop, claim_list in sdc.items():
        for claim_dict in claim_list:
            stmt = Statement.model_validate(claim_dict)
            existing_sdc.append(stmt)

    # Convert labels to Label model objects
    existing_labels = None
    if labels:
        existing_labels = {
            lang: Label.model_validate(lbl) for lang, lbl in labels.items()
        }

    return existing_sdc, existing_labels

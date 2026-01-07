import json
import logging
import time
from tempfile import NamedTemporaryFile
from typing import Any, Optional

import httpx
from mwoauth import AccessToken
from pywikibot.page import FilePage, Page
from pywikibot.tools import compute_file_hash

from curator.app.config import OAUTH_KEY, OAUTH_SECRET
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


class DuplicateUploadError(Exception):
    def __init__(self, duplicates: list[ErrorLink], message: str):
        super().__init__(message)
        self.duplicates = duplicates


def upload_file_chunked(
    file_name: str,
    file_url: str,
    wikitext: str,
    edit_summary: str,
    access_token: AccessToken,
    username: str,
    upload_id: int,
    batch_id: int,
    sdc: Optional[list[Statement]] = None,
    labels: Optional[Label] = None,
) -> dict:
    """
    Upload a file to Commons using Pywikibot's UploadRobot, with optional user OAuth authentication.

    - Uses chunked uploads
    - Sets authentication
    - Returns a dict payload {"result": "success", "title": ..., "url": ...}.
    """
    _ensure_pywikibot()

    site = get_commons_site(access_token, username)

    with NamedTemporaryFile() as temp_file:
        temp_file.write(download_file(file_url, upload_id, batch_id))

        file_hash = compute_file_hash(temp_file.name)
        logger.info(f"[{upload_id}/{batch_id}] file hash: {file_hash}")

        duplicates_list = find_duplicates(site, file_hash)
        if len(duplicates_list) > 0:
            raise DuplicateUploadError(
                duplicates_list, f"File {file_name} already exists on Commons"
            )

        commons_file = build_file_page(site, file_name)
        uploaded = perform_upload(commons_file, temp_file.name, wikitext, edit_summary)

    ensure_uploaded(commons_file, uploaded, file_name)
    apply_sdc(site, commons_file, sdc, edit_summary, labels)

    return {
        "result": "success",
        "title": commons_file.title(with_ns=False),
        "url": commons_file.full_url(),
    }


def get_commons_site(access_token: AccessToken, username: str):
    _ensure_pywikibot()
    assert config
    assert pywikibot

    config.authenticate["commons.wikimedia.org"] = (OAUTH_KEY, OAUTH_SECRET) + tuple(
        access_token
    )
    config.usernames["commons"]["commons"] = username
    config.put_throttle = 0
    site = pywikibot.Site("commons", "commons", user=username)
    site.login()

    return site


def download_file(file_url: str, upload_id: int = 0, batch_id: int = 0) -> bytes:
    """
    Download a file from the given URL with retry logic for Mapillary errors

    When Mapillary returns application/x-php instead of an image, retry after a delay
    """
    for attempt in range(MAX_DOWNLOAD_RETRIES):
        resp = httpx.get(file_url, timeout=60)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "application/x-php" not in content_type:
            return resp.content

        # Got application/x-php instead of image
        if attempt < MAX_DOWNLOAD_RETRIES - 1:
            logger.warning(
                f"[{upload_id}/{batch_id}] Received application/x-php instead of image, "
                f"retrying in 2 seconds... (attempt {attempt + 1}/{MAX_DOWNLOAD_RETRIES})"
            )
            time.sleep(2)
        else:
            raise ValueError(
                f"Failed to download image from {file_url}: received application/x-php content type after {MAX_DOWNLOAD_RETRIES} retries"
            )

    raise ValueError(f"Failed to download file after {MAX_DOWNLOAD_RETRIES} attempts")


def find_duplicates(site, sha1: str) -> list[ErrorLink]:
    return [
        ErrorLink(title=p.title(with_ns=False), url=p.full_url())
        for p in site.allimages(sha1=sha1)
    ]


def build_file_page(site, file_name: str) -> FilePage:
    _ensure_pywikibot()

    return FilePage(Page(site, title=file_name, ns=6))


def perform_upload(
    file_page: FilePage, source_path: str, wikitext: str, edit_summary: str
) -> bool:
    return file_page.upload(
        source=source_path,
        text=wikitext,
        comment=edit_summary,
        ignore_warnings=False,
        chunk_size=1024 * 1024 * 1,
    )


def ensure_uploaded(file_page: FilePage, uploaded: bool, file_name: str):
    if not uploaded and file_page.exists():
        raise ValueError(f"File {file_name} already exists on Commons")

    if not file_page.exists():
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
    site,
    file_page: FilePage,
    sdc: Optional[list[Statement]] = None,
    edit_summary: str = "",
    labels: Optional[Label] = None,
) -> bool:
    """
    Apply SDC to an existing file on Commons
    """
    _ensure_pywikibot()
    assert pywikibot

    data = _build_sdc_payload(sdc, labels)

    if not data:
        return False

    payload = {
        "action": "wbeditentity",
        "site": "commonswiki",
        "title": file_page.title(),
        "data": json.dumps(data),
        "token": site.get_tokens("csrf")["csrf"],
        "summary": edit_summary,
        "bot": False,
    }

    site.simple_request(**payload).submit()
    content = file_page.get(force=True) + "\n"
    file_page.text = content
    file_page.save(summary="null edit")

    return True


def check_title_blacklisted(
    access_token: AccessToken,
    username: str,
    filename: str,
    upload_id: int,
    batch_id: int,
) -> tuple[bool, str]:
    """
    Check if a filename is blacklisted on Wikimedia Commons using the title blacklist API
    """
    site = get_commons_site(access_token, username)

    try:
        response = site.simple_request(
            action="titleblacklist",
            tbaction="create",
            tbtitle=f"File:{filename}",
            format="json",
        )

        data = response.submit()

        if (
            "titleblacklist" in data
            and data["titleblacklist"].get("result") == "blacklisted"
        ):
            reason = data["titleblacklist"].get("reason", "Title is blacklisted")
            return True, reason

        return False, ""

    except Exception as e:
        # Log the error but return False to allow the upload to continue
        # We don't want to block uploads due to title blacklist API issues
        logger.warning(
            f"[{upload_id}/{batch_id}] Failed to check title blacklist for {filename}: {e}"
        )
        return False, ""


def fetch_sdc_from_api(
    site, media_id: str
) -> tuple[list[Statement] | None, dict[str, Label] | None]:
    """
    Fetch SDC data and labels from Commons API for a given media ID using site.simple_request()
    """
    try:
        response = site.simple_request(
            action="wbgetentities",
            ids=media_id,
            format="json",
            props="claims|labels",
        )
        data = response.submit()

        # Check if the entity exists
        if media_id not in data.get("entities", {}):
            logger.warning(f"Media ID {media_id} not found on Commons")
            return None, None

        entity = data["entities"][media_id]

        # Convert statements - API returns 'statements' key, not 'claims'
        statements_data = entity.get("statements", {})
        existing_sdc = []
        for prop, claim_list in statements_data.items():
            for claim_dict in claim_list:
                stmt = Statement.model_validate(claim_dict)
                existing_sdc.append(stmt)

        # Convert labels to Label model objects
        labels_data = entity.get("labels", {})
        existing_labels = None
        if labels_data:
            existing_labels = {
                lang_code: Label.model_validate(label_data)
                for lang_code, label_data in labels_data.items()
            }

        return existing_sdc, existing_labels

    except Exception as e:
        logger.error(f"Failed to fetch SDC for {media_id}: {e}")
        return None, None

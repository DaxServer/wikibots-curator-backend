import json
import logging
from tempfile import NamedTemporaryFile
from typing import Any, Optional

import httpx
from mwoauth import AccessToken

from curator.app.config import OAUTH_KEY, OAUTH_SECRET
from curator.asyncapi import ErrorLink, Label, Statement

logger = logging.getLogger(__name__)


pywikibot: Any | None = None
config: Any | None = None
Page: Any | None = None
FilePage: Any | None = None
compute_file_hash: Any | None = None


def _ensure_pywikibot() -> None:
    global pywikibot, config, Page, FilePage, compute_file_hash
    if pywikibot is None or config is None:
        import pywikibot as _pywikibot
        import pywikibot.config as _config

        if pywikibot is None:
            pywikibot = _pywikibot
        if config is None:
            config = _config

    if compute_file_hash is None:
        from pywikibot.tools import compute_file_hash as _compute_file_hash

        compute_file_hash = _compute_file_hash

    if Page is None or FilePage is None:
        from pywikibot import FilePage as _FilePage
        from pywikibot import Page as _Page

        if Page is None:
            Page = _Page
        if FilePage is None:
            FilePage = _FilePage


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
    assert compute_file_hash

    site = get_commons_site(access_token, username)

    logger.info(f"Uploading file {file_name} from {file_url}")

    with NamedTemporaryFile() as temp_file:
        temp_file.write(download_file(file_url))

        file_hash = compute_file_hash(temp_file.name)
        logger.info(f"File hash: {file_hash}")

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


def download_file(file_url: str) -> bytes:
    resp = httpx.get(file_url, timeout=60)
    resp.raise_for_status()

    return resp.content


def find_duplicates(site, sha1: str) -> list[ErrorLink]:
    return [
        ErrorLink(title=p.title(with_ns=False), url=p.full_url())
        for p in site.allimages(sha1=sha1)
    ]


def build_file_page(site, file_name: str):
    _ensure_pywikibot()
    assert FilePage
    assert Page

    return FilePage(Page(site, title=file_name, ns=6))


def perform_upload(
    file_page, source_path: str, wikitext: str, edit_summary: str
) -> bool:
    return file_page.upload(
        source=source_path,
        text=wikitext,
        comment=edit_summary,
        ignore_warnings=False,
        chunk_size=1024 * 1024 * 2,
    )


def ensure_uploaded(file_page, uploaded: bool, file_name: str):
    if not uploaded and file_page.exists():
        raise ValueError(f"File {file_name} already exists on Commons")

    if not file_page.exists():
        raise ValueError("File upload failed")


def apply_sdc(
    site,
    file_page,
    sdc: Optional[list[Statement]] = None,
    edit_summary: str = "",
    labels: Optional[Label] = None,
):
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

    if not data:
        return

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


def check_title_blacklisted(
    access_token: AccessToken, username: str, filename: str
) -> tuple[bool, str]:
    """
    Check if a filename is blacklisted on Wikimedia Commons using the title blacklist API.

    Args:
        access_token: The OAuth access token for Commons API
        username: The Commons username for authentication
        filename: The filename to check (without "File:" prefix)

    Returns:
        tuple: (is_blacklisted, reason) where is_blacklisted is True if blacklisted,
               and reason is the blacklist reason or empty string if not blacklisted
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
        logger.warning(f"Failed to check title blacklist for {filename}: {e}")
        return False, ""

from tempfile import NamedTemporaryFile
import httpx
from pywikibot import Page
from pywikibot import FilePage
from typing import List
import json
from curator.app.config import OAUTH_KEY
from curator.app.config import OAUTH_SECRET
from typing import Optional
import pywikibot
import pywikibot.config as config
from mwoauth import AccessToken
from pywikibot.tools import compute_file_hash


def upload_file_chunked(
    file_name: str,
    file_url: str,
    wikitext: str,
    edit_summary: str,
    access_token: AccessToken,
    username: str,
    sdc: Optional[List[dict]] = None,
) -> dict:
    """
    Upload a file to Commons using Pywikibot's UploadRobot, with optional user OAuth authentication.

    - Uses chunked uploads
    - Sets authentication
    - Returns a dict payload {"result": "success", "title": ..., "url": ...}.
    """

    site = get_commons_site(access_token, username)

    print(file_name)
    print(file_url)

    temp_file = NamedTemporaryFile()
    temp_file.write(download_file(file_url))

    file_hash = compute_file_hash(temp_file.name)
    print(file_hash)

    duplicates_list = find_duplicates(site, file_hash)
    if len(duplicates_list) > 0:
        raise ValueError(
            f"File {file_name} already exists on Commons at {duplicates_list}"
        )

    commons_file = build_file_page(site, file_name)
    uploaded = perform_upload(commons_file, temp_file.name, wikitext, edit_summary)

    ensure_uploaded(commons_file, uploaded, file_name)

    apply_sdc(site, commons_file, sdc, edit_summary)

    return {
        "result": "success",
        "title": commons_file.title(with_ns=False),
        "url": commons_file.full_url(),
    }


def get_commons_site(access_token: AccessToken, username: str):
    config.authenticate["commons.wikimedia.org"] = (OAUTH_KEY, OAUTH_SECRET) + tuple(
        access_token
    )
    config.usernames["commons"]["commons"] = username
    config.put_throttle = 0
    site = pywikibot.Site("commons", "commons", user=username)
    site.login()

    return site


def download_file(file_url: str) -> bytes:
    resp = httpx.get(file_url)
    resp.raise_for_status()

    return resp.content


def find_duplicates(site, sha1: str) -> List[dict]:
    return [
        {"title": p.title(with_ns=False), "url": p.full_url()}
        for p in site.allimages(sha1=sha1)
    ]


def build_file_page(site, file_name: str):
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
        watch=True,
    )


def ensure_uploaded(file_page, uploaded: bool, file_name: str):
    if not uploaded and file_page.exists():
        raise ValueError(f"File {file_name} already exists on Commons")

    if not file_page.exists():
        raise ValueError("File upload failed")


def apply_sdc(site, file_page, sdc: Optional[List[dict]], edit_summary: str):
    if not sdc:
        return

    payload = {
        "action": "wbeditentity",
        "site": "commonswiki",
        "title": file_page.title(),
        "data": json.dumps({"claims": sdc}),
        "token": site.get_tokens("csrf")["csrf"],
        "summary": edit_summary,
        "bot": False,
    }

    site.simple_request(**payload).submit()
    content = file_page.get(force=True) + "\n"
    file_page.text = content
    file_page.save(summary="null edit")

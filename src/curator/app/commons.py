from typing import List
import json
from curator.app.config import OAUTH_KEY
from curator.app.config import OAUTH_SECRET
from typing import Optional
import pywikibot
import pywikibot.config as config
from pywikibot.specialbots import UploadRobot
from mwoauth import AccessToken


def upload_file_chunked(
    filename: str,
    file_path: str,
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

    config.authenticate['commons.wikimedia.org'] = (OAUTH_KEY, OAUTH_SECRET) + tuple(access_token)
    config.usernames['commons']['commons'] = username
    site = pywikibot.Site('commons', 'commons', user=username)
    site.login()

    print(filename)
    print(file_path)

    bot = UploadRobot(
        url=file_path,
        description=wikitext,
        use_filename=filename,
        keep_filename=True,
        summary=edit_summary,
        verify_description=False,
        chunk_size=1024 * 1024 * 2, # 2MB chunks
        target_site=site,
        asynchronous=True,
        always=True,
        aborts=True,
    )
    filename = bot.upload_file(file_path)
    bot.exit()

    commons_file = pywikibot.Page(site, filename, ns=6)

    if not commons_file.exists():
        raise ValueError("Upload failed")

    # if sdc:
    #     payload = {
    #         "action": "wbeditentity",
    #         "site": "commonswiki",
    #         "title": commons_file.title(),
    #         "data": json.dumps({"claims": sdc}),
    #         "token": site.get_tokens("csrf")["csrf"],
    #         "summary": edit_summary,
    #         "bot": False,
    #     }
    #     print(payload)
    #     # site.simple_request(**payload).submit()

    return {"result": "success", "title": commons_file.title(with_ns=False), "url": commons_file.full_url()}

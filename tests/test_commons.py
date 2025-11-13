from unittest.mock import patch
from mwoauth import AccessToken

from curator.app.commons import upload_file_chunked


def test_upload_file_chunked():
    # Mock parameters
    filename = "test.jpg"
    file_path = "/tmp/test.jpg"
    wikitext = "Test description"
    edit_summary = "Test upload"
    username = "testuser"

    access_token = AccessToken("access_token", "access_secret")

    # Mock pywikibot config and Site
    with (
        patch("curator.app.commons.config") as mock_config,
        patch("pywikibot.Site") as mock_site,
        patch("httpx.get") as mock_httpx_get,
        patch("curator.app.commons.Page") as mock_page,
        patch("curator.app.commons.FilePage") as mock_file_page,
        patch("curator.app.commons.compute_file_hash") as mock_compute_hash,
        patch("curator.app.commons.OAUTH_KEY", "key"),
        patch("curator.app.commons.OAUTH_SECRET", "secret"),
    ):

        mock_site_instance = mock_site.return_value
        mock_site_instance.login.return_value = None

        mock_site_instance.allimages.return_value = []
        mock_httpx_get.return_value.content = b"abc"
        mock_httpx_get.return_value.raise_for_status.return_value = None

        mock_page_instance = mock_page.return_value
        mock_page_instance.exists.return_value = True
        mock_page_instance.title.return_value = filename
        mock_page_instance.full_url.return_value = (
            "https://commons.wikimedia.org/wiki/File:test.jpg"
        )

        mock_compute_hash.return_value = "deadbeef"

        mock_file_page_instance = mock_file_page.return_value
        mock_file_page_instance.upload.return_value = True
        mock_file_page_instance.exists.return_value = True
        mock_file_page_instance.title.return_value = filename
        mock_file_page_instance.full_url.return_value = (
            "https://commons.wikimedia.org/wiki/File:test.jpg"
        )

        result = upload_file_chunked(
            filename,
            file_path,
            wikitext,
            edit_summary,
            access_token=access_token,
            username=username,
            sdc=None,
        )

        # Assert config was set
        mock_config.authenticate.__setitem__.assert_called_with(
            "commons.wikimedia.org", ("key", "secret", "access_token", "access_secret")
        )
        mock_config.usernames.__getitem__.assert_called_with("commons")
        inner_dict = mock_config.usernames.__getitem__.return_value
        inner_dict.__setitem__.assert_called_with("commons", username)

        # Assert site creation and login
        mock_site.assert_called_with("commons", "commons", user=username)
        mock_site_instance.login.assert_called_once()

        mock_httpx_get.assert_called_with(file_path, timeout=60)

        mock_page.assert_called_with(mock_site_instance, title=filename, ns=6)
        mock_file_page.assert_called()

        # Assert result
        assert result == {
            "result": "success",
            "title": filename,
            "url": "https://commons.wikimedia.org/wiki/File:test.jpg",
        }

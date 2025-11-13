from unittest.mock import MagicMock, patch

from curator.app.commons import (
    get_commons_site,
    download_file,
    find_duplicates,
    build_file_page,
    perform_upload,
    ensure_uploaded,
    apply_sdc,
)
import pytest


def test_get_commons_site_sets_auth_and_logs_in():
    with (
        patch("curator.app.commons.config") as mock_config,
        patch("pywikibot.Site") as mock_site,
        patch("curator.app.commons.OAUTH_KEY", "key"),
        patch("curator.app.commons.OAUTH_SECRET", "secret"),
    ):
        access_token = ("access_token", "access_secret")
        get_commons_site(access_token, "user")
        mock_config.authenticate.__setitem__.assert_called()
        mock_config.usernames.__getitem__.assert_called_with("commons")
        mock_site.assert_called_with("commons", "commons", user="user")
        mock_site.return_value.login.assert_called_once()


def test_download_file_returns_bytes():
    with patch("httpx.get") as mock_get:
        mock_get.return_value.content = b"abc"
        mock_get.return_value.raise_for_status.return_value = None
        data = download_file("http://example.com/file.jpg")
        assert data == b"abc"


def test_find_duplicates_returns_list():
    site = MagicMock()
    p = MagicMock()
    p.title.return_value = "t"
    p.full_url.return_value = "u"
    site.allimages.return_value = [p]
    result = find_duplicates(site, "sha1")
    assert result == [{"title": "t", "url": "u"}]


def test_build_file_page_uses_named_title():
    with (
        patch("curator.app.commons.Page") as mock_page,
        patch("curator.app.commons.FilePage") as mock_file_page,
    ):
        site = MagicMock()
        fp = build_file_page(site, "x.jpg")
        mock_page.assert_called_with(site, title="x.jpg", ns=6)
        assert fp is mock_file_page.return_value


def test_perform_upload_passes_args():
    file_page = MagicMock()
    perform_upload(file_page, "/tmp/x", "w", "s")
    file_page.upload.assert_called()


def test_ensure_uploaded_raises_on_exists_without_uploaded():
    file_page = MagicMock()
    file_page.exists.return_value = True
    with pytest.raises(ValueError):
        ensure_uploaded(file_page, False, "x.jpg")


def test_apply_sdc_invokes_simple_request_and_null_edit():
    site = MagicMock()
    req = MagicMock()
    site.simple_request.return_value = req
    fp = MagicMock()
    fp.title.return_value = "File:x.jpg"
    apply_sdc(site, fp, [{"x": 1}], "summary")
    site.simple_request.assert_called()
    fp.save.assert_called()

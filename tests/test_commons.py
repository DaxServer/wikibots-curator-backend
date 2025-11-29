from unittest.mock import MagicMock, patch
import pytest
from mwoauth import AccessToken

from curator.app.commons import (
    get_commons_site,
    download_file,
    find_duplicates,
    build_file_page,
    perform_upload,
    ensure_uploaded,
    apply_sdc,
    upload_file_chunked,
)


# --- Helper Functions Tests ---


def test_get_commons_site_sets_auth_and_logs_in():
    with (
        patch("curator.app.commons.config") as mock_config,
        patch("curator.app.commons.pywikibot") as mock_pywikibot,
        patch("curator.app.commons.OAUTH_KEY", "key"),
        patch("curator.app.commons.OAUTH_SECRET", "secret"),
    ):
        access_token = ("access_token", "access_secret")
        get_commons_site(access_token, "user")
        mock_config.authenticate.__setitem__.assert_called()
        mock_config.usernames.__getitem__.assert_called_with("commons")
        mock_pywikibot.Site.assert_called_with("commons", "commons", user="user")
        mock_pywikibot.Site.return_value.login.assert_called_once()


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


def test_apply_sdc_includes_labels_in_payload_when_provided():
    site = MagicMock()
    req = MagicMock()
    site.simple_request.return_value = req
    site.get_tokens.return_value = {"csrf": "token"}
    fp = MagicMock()
    fp.title.return_value = "File:x.jpg"
    labels = {"en": {"language": "en", "value": "Example"}}
    apply_sdc(site, fp, [{"x": 1}], "summary", labels)
    called_kwargs = site.simple_request.call_args.kwargs
    assert "data" in called_kwargs
    assert "labels" in __import__("json").loads(called_kwargs["data"])


# --- Main Integration Test ---


def test_upload_file_chunked():
    # Mock parameters
    filename = "test.jpg"
    file_path = "/tmp/test.jpg"
    wikitext = (
        "== {{int:filedesc}} ==\n"
        "{{Information\n"
        " | description = {{en|1=Example label}}\n"
        " | source      = {{Mapillary-source|key=abc}}\n"
        "}}\n"
    )
    edit_summary = "Test upload"
    username = "testuser"

    access_token = AccessToken("access_token", "access_secret")

    # Mock pywikibot config and Site
    with (
        patch("curator.app.commons.config") as mock_config,
        patch("curator.app.commons.pywikibot") as mock_pywikibot,
        patch("httpx.get") as mock_httpx_get,
        patch("curator.app.commons.Page") as mock_page,
        patch("curator.app.commons.FilePage") as mock_file_page,
        patch("curator.app.commons.compute_file_hash") as mock_compute_hash,
        patch("curator.app.commons.OAUTH_KEY", "key"),
        patch("curator.app.commons.OAUTH_SECRET", "secret"),
    ):
        mock_site = mock_pywikibot.Site
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

        # Spy on simple_request to capture payload
        simple_request = mock_site_instance.simple_request

        result = upload_file_chunked(
            filename,
            file_path,
            wikitext,
            edit_summary,
            access_token=access_token,
            username=username,
            sdc=[{"mainsnak": {}}],
            labels={"en": {"language": "en", "value": "Example label"}},
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

        # Assert labels were included in wbeditentity data
        assert simple_request.called
        kwargs = simple_request.call_args.kwargs
        assert "data" in kwargs
        payload = __import__("json").loads(kwargs["data"])
        assert "labels" in payload
        assert payload["labels"] == [
            {"en": {"language": "en", "value": "Example label"}}
        ]

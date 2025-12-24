from unittest.mock import MagicMock, patch

import pytest

from curator.app.commons import (
    apply_sdc,
    build_file_page,
    download_file,
    ensure_uploaded,
    find_duplicates,
    get_commons_site,
    perform_upload,
    upload_file_chunked,
)
from curator.asyncapi import (
    ErrorLink,
    Label,
    NoValueSnak,
    Rank,
    Statement,
    StringDataValue,
    StringValueSnak,
)


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
    assert result == [ErrorLink(title="t", url="u")]


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
    sdc = [Statement(mainsnak=NoValueSnak(property="P180"), rank=Rank.NORMAL)]
    apply_sdc(site, fp, sdc=sdc, edit_summary="summary", labels=None)
    site.simple_request.assert_called()
    fp.save.assert_called()


def test_apply_sdc_includes_labels_in_payload_when_provided():
    site = MagicMock()
    req = MagicMock()
    site.simple_request.return_value = req
    site.get_tokens.return_value = {"csrf": "token"}
    fp = MagicMock()
    fp.title.return_value = "File:x.jpg"
    labels = Label(language="en", value="Example")
    sdc = [Statement(mainsnak=NoValueSnak(property="P180"), rank=Rank.NORMAL)]
    apply_sdc(site, fp, sdc, "summary", labels)
    called_kwargs = site.simple_request.call_args.kwargs
    assert "data" in called_kwargs
    assert "labels" in __import__("json").loads(called_kwargs["data"])


def test_upload_file_chunked():
    with (
        patch("curator.app.commons.get_commons_site") as mock_get_site,
        patch("curator.app.commons.download_file") as mock_download,
        patch("curator.app.commons.compute_file_hash") as mock_hash,
        patch("curator.app.commons.find_duplicates") as mock_find_duplicates,
        patch("curator.app.commons.build_file_page") as mock_build_page,
        patch("curator.app.commons.ensure_uploaded") as mock_ensure,
        patch("curator.app.commons.apply_sdc") as mock_apply_sdc,
    ):
        site = MagicMock()
        mock_get_site.return_value = site
        mock_download.return_value = b"data"
        mock_hash.return_value = "hash"
        mock_find_duplicates.return_value = []
        mock_ensure.return_value = True
        file_page = MagicMock()
        mock_build_page.return_value = file_page
        file_page.full_url.return_value = "url"
        file_page.title.return_value = "t"

        access_token = ("t", "s")
        username = "user"
        sdc = [
            Statement(
                mainsnak=StringValueSnak(
                    property="P180", datavalue=StringDataValue(value="Q42")
                ),
                rank=Rank.NORMAL,
            )
        ]
        labels = Label(language="en", value="Example label")

        result = upload_file_chunked(
            file_name="x.jpg",
            file_url="url",
            wikitext="w",
            edit_summary="s",
            access_token=access_token,
            username=username,
            sdc=sdc,
            labels=labels,
        )

        assert result == {
            "result": "success",
            "title": "t",
            "url": "url",
        }
        mock_apply_sdc.assert_called_with(site, file_page, sdc, "s", labels)

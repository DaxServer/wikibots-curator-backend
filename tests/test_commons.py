from unittest.mock import patch

import pytest

from curator.app.commons import (
    apply_sdc,
    build_file_page,
    check_title_blacklisted,
    download_file,
    ensure_uploaded,
    find_duplicates,
    get_commons_site,
    perform_upload,
    upload_file_chunked,
)
from curator.asyncapi import Label, Statement
from curator.asyncapi.ErrorLink import ErrorLink
from curator.asyncapi.NoValueSnak import NoValueSnak
from curator.asyncapi.Rank import Rank


@pytest.fixture
def mock_commons_site(mocker):
    """Mock the get_commons_site function"""
    return mocker.patch("curator.app.commons.get_commons_site")


def test_get_commons_site_sets_auth_and_logs_in(mocker):
    """Test that get_commons_site sets authentication and logs in"""
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


def test_download_file_returns_bytes(mocker, mock_get, mock_requests_response):
    """Test that download_file returns file bytes"""
    mock_requests_response.content = b"abc"
    mock_get.return_value = mock_requests_response

    data = download_file("http://example.com/file.jpg")
    assert data == b"abc"


def test_download_file_with_error(mocker, mock_get, mock_requests_response):
    """Test that download_file handles errors gracefully"""
    mock_requests_response.content = b""
    mock_get.return_value = mock_requests_response

    data = download_file("http://example.com/file.jpg")
    assert data == b""


def test_find_duplicates_returns_list(mocker):
    """Test that find_duplicates returns list of ErrorLink objects"""
    site = mocker.MagicMock()
    p = mocker.MagicMock()
    p.title.return_value = "t"
    p.full_url.return_value = "u"
    site.allimages.return_value = [p]
    result = find_duplicates(site, "sha1")
    assert result == [ErrorLink(title="t", url="u")]


def test_build_file_page_uses_named_title(mocker):
    """Test that build_file_page uses named title"""
    with (
        patch("curator.app.commons.Page") as mock_page,
        patch("curator.app.commons.FilePage") as mock_file_page,
    ):
        site = mocker.MagicMock()
        fp = build_file_page(site, "x.jpg")
        mock_page.assert_called_with(site, title="x.jpg", ns=6)
        assert fp is mock_file_page.return_value


def test_perform_upload_passes_args(mocker):
    """Test that perform_upload passes arguments correctly"""
    file_page = mocker.MagicMock()
    perform_upload(file_page, "/tmp/x", "w", "s")
    file_page.upload.assert_called()


def test_ensure_uploaded_raises_on_exists_without_uploaded(mocker):
    """Test that ensure_uploaded raises ValueError when file exists but not uploaded"""
    file_page = mocker.MagicMock()
    file_page.exists.return_value = True
    with pytest.raises(ValueError):
        ensure_uploaded(file_page, False, "x.jpg")


def test_apply_sdc_invokes_simple_request_and_null_edit(mocker):
    """Test that apply_sdc invokes simple_request and null edit"""
    site = mocker.MagicMock()
    req = mocker.MagicMock()
    site.simple_request.return_value = req
    fp = mocker.MagicMock()
    fp.title.return_value = "File:x.jpg"

    no_value_snak = NoValueSnak(property="P180")
    statement = Statement(
        mainsnak=no_value_snak,
        rank=Rank.NORMAL,
    )
    sdc = [statement]

    apply_sdc(site, fp, sdc=sdc, edit_summary="summary", labels=None)
    site.simple_request.assert_called()
    fp.save.assert_called()


def test_upload_file_chunked(mocker, mock_commons_site):
    """Test that upload_file_chunked works correctly"""
    with (
        patch("curator.app.commons.download_file") as mock_download,
        patch("curator.app.commons.compute_file_hash") as mock_hash,
        patch("curator.app.commons.find_duplicates") as mock_find_duplicates,
        patch("curator.app.commons.build_file_page") as mock_build_page,
        patch("curator.app.commons.ensure_uploaded") as mock_ensure,
        patch("curator.app.commons.apply_sdc") as mock_apply_sdc,
    ):
        site = mocker.MagicMock()
        mock_commons_site.return_value = site
        mock_download.return_value = b"data"
        mock_hash.return_value = "hash"
        mock_find_duplicates.return_value = []
        mock_ensure.return_value = True
        file_page = mocker.MagicMock()
        mock_build_page.return_value = file_page
        file_page.full_url.return_value = "url"
        file_page.title.return_value = "t"

        access_token = mocker.MagicMock()
        username = "user"

        no_value_snak = NoValueSnak(property="P180")
        statement = Statement(
            mainsnak=no_value_snak,
            rank=Rank.NORMAL,
        )
        sdc = [statement]

        label = Label(language="en", value="Example label")
        labels = label

        result = upload_file_chunked(
            file_name="x.jpg",
            file_url="url",
            wikitext="w",
            edit_summary="s",
            access_token=access_token,
            username=username,
            upload_id=1,
            batch_id=1,
            sdc=sdc,
            labels=labels,
        )

        assert result == {
            "result": "success",
            "title": "t",
            "url": "url",
        }
        mock_apply_sdc.assert_called_with(site, file_page, sdc, "s", labels)


def test_check_title_blacklisted_returns_true_when_blacklisted(
    mocker, mock_commons_site
):
    """Test check_title_blacklisted when title is blacklisted."""
    access_token = mocker.MagicMock()
    username = "testuser"

    # Mock get_commons_site
    site = mocker.MagicMock()
    req = mocker.MagicMock()
    mock_commons_site.return_value = site
    site.simple_request.return_value = req

    # Mock the API response for blacklisted title
    req.submit.return_value = {
        "titleblacklist": {
            "result": "blacklisted",
            "reason": "Title contains blacklisted pattern",
        }
    }

    is_blacklisted, reason = check_title_blacklisted(
        access_token, username, "test_file.jpg", 1, 1
    )

    assert is_blacklisted is True
    assert reason == "Title contains blacklisted pattern"
    site.simple_request.assert_called_with(
        action="titleblacklist",
        tbaction="create",
        tbtitle="File:test_file.jpg",
        format="json",
    )


def test_check_title_blacklisted_returns_false_when_not_blacklisted(
    mocker, mock_commons_site
):
    """Test check_title_blacklisted when title is not blacklisted."""
    access_token = mocker.MagicMock()
    username = "testuser"

    site = mocker.MagicMock()
    req = mocker.MagicMock()
    mock_commons_site.return_value = site
    site.simple_request.return_value = req

    # Mock the API response for non-blacklisted title
    req.submit.return_value = {"titleblacklist": {"result": "ok"}}

    is_blacklisted, reason = check_title_blacklisted(
        access_token, username, "test_file.jpg", 1, 1
    )

    assert is_blacklisted is False
    assert reason == ""
    site.simple_request.assert_called_with(
        action="titleblacklist",
        tbaction="create",
        tbtitle="File:test_file.jpg",
        format="json",
    )


def test_check_title_blacklisted_returns_false_on_api_error(mocker, mock_commons_site):
    """Test check_title_blacklisted when API call fails."""
    access_token = mocker.MagicMock()
    username = "testuser"

    site = mocker.MagicMock()
    mock_commons_site.return_value = site
    site.simple_request.side_effect = Exception("API Error")

    is_blacklisted, reason = check_title_blacklisted(
        access_token, username, "test_file.jpg", 1, 1
    )

    assert is_blacklisted is False
    assert reason == ""


def test_check_title_blacklisted_uses_default_reason_when_missing(
    mocker, mock_commons_site
):
    """Test check_title_blacklisted uses default reason when not provided."""
    access_token = mocker.MagicMock()
    username = "testuser"

    site = mocker.MagicMock()
    req = mocker.MagicMock()
    mock_commons_site.return_value = site
    site.simple_request.return_value = req

    # Mock the API response for blacklisted title without reason
    req.submit.return_value = {"titleblacklist": {"result": "blacklisted"}}

    is_blacklisted, reason = check_title_blacklisted(
        access_token, username, "test_file.jpg", 1, 1
    )

    assert is_blacklisted is True
    assert reason == "Title is blacklisted"


def test_apply_sdc_without_labels(mocker):
    """Test that apply_sdc works without labels"""
    site = mocker.MagicMock()
    req = mocker.MagicMock()
    site.simple_request.return_value = req
    site.get_tokens.return_value = {"csrf": "token"}
    fp = mocker.MagicMock()
    fp.title.return_value = "File:x.jpg"

    no_value_snak = NoValueSnak(property="P180")
    statement = Statement(
        mainsnak=no_value_snak,
        rank=Rank.NORMAL,
    )
    sdc = [statement]

    apply_sdc(site, fp, sdc=sdc, edit_summary="summary")

    site.simple_request.assert_called_once_with(
        action="wbeditentity",
        site="commonswiki",
        title="File:x.jpg",
        data='{"claims": [{"mainsnak": {"snaktype": "novalue", "property": "P180"}, "rank": "normal", "qualifiers": {}, "qualifiers-order": [], "references": [], "type": "statement"}]}',
        token="token",
        summary="summary",
        bot=False,
    )


def test_apply_sdc_includes_labels_in_payload_when_provided(mocker):
    """Test that apply_sdc includes labels in payload when provided"""
    site = mocker.MagicMock()
    req = mocker.MagicMock()
    site.simple_request.return_value = req
    site.get_tokens.return_value = {"csrf": "token"}
    fp = mocker.MagicMock()
    fp.title.return_value = "File:x.jpg"

    no_value_snak = NoValueSnak(property="P180")
    statement = Statement(
        mainsnak=no_value_snak,
        rank=Rank.NORMAL,
    )
    sdc = [statement]

    label = Label(language="en", value="Test Label")
    labels = label

    apply_sdc(site, fp, sdc=sdc, edit_summary="summary", labels=labels)

    site.simple_request.assert_called_once_with(
        action="wbeditentity",
        site="commonswiki",
        title="File:x.jpg",
        data='{"claims": [{"mainsnak": {"snaktype": "novalue", "property": "P180"}, "rank": "normal", "qualifiers": {}, "qualifiers-order": [], "references": [], "type": "statement"}], "labels": [{"language": "en", "value": "Test Label"}]}',
        token="token",
        summary="summary",
        bot=False,
    )


def test_apply_sdc_without_sdc(mocker):
    """Test that apply_sdc works without SDC"""
    site = mocker.MagicMock()
    req = mocker.MagicMock()
    site.simple_request.return_value = req
    site.get_tokens.return_value = {"csrf": "token"}
    fp = mocker.MagicMock()
    fp.title.return_value = "File:x.jpg"

    label = Label(language="en", value="Test Label")
    labels = label

    apply_sdc(site, fp, edit_summary="summary", labels=labels)

    site.simple_request.assert_called_once_with(
        action="wbeditentity",
        site="commonswiki",
        title="File:x.jpg",
        data='{"labels": [{"language": "en", "value": "Test Label"}]}',
        token="token",
        summary="summary",
        bot=False,
    )


def test_apply_sdc_with_empty_data(mocker):
    """Test that apply_sdc works with empty data"""
    site = mocker.MagicMock()
    req = mocker.MagicMock()
    site.simple_request.return_value = req
    site.get_tokens.return_value = {"csrf": "token"}
    fp = mocker.MagicMock()
    fp.title.return_value = "File:x.jpg"

    apply_sdc(site, fp, edit_summary="summary")

    # When no SDC data or labels are provided, apply_sdc should return early
    # without calling simple_request
    site.simple_request.assert_not_called()


def test_apply_sdc_with_file_page_object(mocker):
    """Test that apply_sdc works with FilePage object"""
    site = mocker.MagicMock()
    req = mocker.MagicMock()
    site.simple_request.return_value = req
    site.get_tokens.return_value = {"csrf": "token"}

    # Create a mock FilePage
    fp = mocker.MagicMock()
    fp.title.return_value = "File:test.jpg"

    no_value_snak = NoValueSnak(property="P180")
    statement = Statement(
        mainsnak=no_value_snak,
        rank=Rank.NORMAL,
    )
    sdc = [statement]

    apply_sdc(site, fp, sdc=sdc, edit_summary="summary")

    site.simple_request.assert_called_once_with(
        action="wbeditentity",
        site="commonswiki",
        title="File:test.jpg",
        data='{"claims": [{"mainsnak": {"snaktype": "novalue", "property": "P180"}, "rank": "normal", "qualifiers": {}, "qualifiers-order": [], "references": [], "type": "statement"}]}',
        token="token",
        summary="summary",
        bot=False,
    )

from unittest.mock import patch, MagicMock

from curator.app.commons import upload_file_chunked


def test_upload_file_chunked():
    # Mock parameters
    filename = "test.jpg"
    file_path = "/tmp/test.jpg"
    wikitext = "Test description"
    edit_summary = "Test upload"
    username = "testuser"

    mock_access_token = MagicMock()
    mock_access_token.key = "access_token"
    mock_access_token.secret = "access_secret"

    # Mock pywikibot config and Site
    with patch('curator.app.commons.config') as mock_config, \
         patch('pywikibot.Site') as mock_site, \
         patch('curator.app.commons.UploadRobot') as mock_upload_robot, \
         patch('pywikibot.Page') as mock_page, \
         patch('curator.app.commons.OAUTH_KEY') as mock_oauth_key, \
         patch('curator.app.commons.OAUTH_SECRET') as mock_oauth_secret:

        mock_oauth_key.return_value = "key"
        mock_oauth_secret.return_value = "secret"

        mock_site_instance = mock_site.return_value
        mock_site_instance.login.return_value = None

        mock_bot_instance = mock_upload_robot.return_value
        mock_bot_instance.upload_file.return_value = filename
        mock_bot_instance.exit.return_value = None

        mock_page_instance = mock_page.return_value
        mock_page_instance.exists.return_value = True
        mock_page_instance.title.return_value = filename
        mock_page_instance.full_url.return_value = "https://commons.wikimedia.org/wiki/File:test.jpg"

        result = upload_file_chunked(
            filename, file_path, wikitext, edit_summary,
            access_token=mock_access_token,
            username=username,
            sdc=None
        )

        # Assert config was set
        mock_config.authenticate.__setitem__.assert_called_with(
            'commons.wikimedia.org',
            (mock_oauth_key.return_value, mock_oauth_secret.return_value, mock_access_token.key, mock_access_token.secret)
        )
        mock_config.usernames.__getitem__.assert_called_with('commons')
        inner_dict = mock_config.usernames.__getitem__.return_value
        inner_dict.__setitem__.assert_called_with('commons', username)

        # Assert site creation and login
        mock_site.assert_called_with('commons', 'commons', user=username)
        mock_site_instance.login.assert_called_once()

        # Assert UploadRobot called correctly
        mock_upload_robot.assert_called_once_with(
            url=file_path,
            description=wikitext,
            use_filename=filename,
            keep_filename=True,
            verify_description=False,
            chunk_size=1024 * 1024 * 2,
            target_site=mock_site_instance,
            summary=edit_summary,
            asynchronous=True,
            always=True,
            aborts=True,
        )
        mock_bot_instance.upload_file.assert_called_with(file_path)
        mock_bot_instance.exit.assert_called_once()

        # Assert Page called
        mock_page.assert_called_with(mock_site_instance, filename, ns=6)

        # Assert result
        assert result == {"result": "success", "title": filename, "url": "https://commons.wikimedia.org/wiki/File:test.jpg"}

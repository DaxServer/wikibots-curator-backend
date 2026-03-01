"""WebSocket handler tests for preset operations."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from curator.app.handler import Handler
from curator.app.models import Preset
from curator.asyncapi import ImageHandler, Label, PresetItem, SavePresetData


@pytest.mark.asyncio
async def test_fetch_presets_sends_presets_list(
    mock_user, mock_sender, patch_get_session
):
    """Test fetch_presets sends PresetsList."""
    # create mock preset
    preset = MagicMock(spec=Preset)
    preset.id = 1
    preset.title = "Test Preset"
    preset.title_template = "{{location}}"
    preset.labels = {"language": "en", "value": "Test"}
    preset.categories = "Test, Category"
    preset.exclude_from_date_category = False
    preset.handler = "mapillary"
    preset.is_default = False
    preset.created_at = datetime(2023, 1, 1)
    preset.updated_at = datetime(2023, 1, 1)

    patch_get_session("curator.app.handler.get_session")
    with patch("curator.app.handler.get_presets_for_handler", return_value=[preset]):
        handler = Handler(mock_user, mock_sender, MagicMock())

        await handler.fetch_presets(ImageHandler.MAPILLARY)

        # verify send_presets_list was called
        mock_sender.send_presets_list.assert_called_once()
        call_args = mock_sender.send_presets_list.call_args

        # check presets list is passed
        presets = call_args[0][1]
        assert len(presets) == 1
        assert isinstance(presets[0], PresetItem)
        assert presets[0].id == 1
        assert presets[0].title == "Test Preset"


@pytest.mark.asyncio
async def test_save_preset_creates_new_preset(
    mock_user, mock_sender, patch_get_session
):
    """Test save_preset creates new preset."""
    data = SavePresetData(
        preset_id=None,
        title="New Preset",
        title_template="{{location}}",
        labels=Label(language="en", value="Test"),
        categories="Test",
        exclude_from_date_category=False,
        is_default=False,
        handler="mapillary",
    )

    patch_get_session("curator.app.handler.get_session")
    with (
        patch("curator.app.handler.create_preset"),
        patch("curator.app.handler.get_presets_for_handler", return_value=[]),
    ):
        handler = Handler(mock_user, mock_sender, MagicMock())

        await handler.save_preset(data)

        # verify no error was raised
        assert True


@pytest.mark.asyncio
async def test_save_preset_updates_existing_preset(
    mock_user, mock_sender, patch_get_session
):
    """Test save_preset updates existing preset."""
    data = SavePresetData(
        preset_id=1,
        title="Updated Preset",
        title_template="{{location}} - Updated",
        labels=Label(language="en", value="Updated"),
        categories="Updated",
        exclude_from_date_category=True,
        is_default=True,
        handler="mapillary",
    )

    mock_preset = MagicMock(spec=Preset)
    patch_get_session("curator.app.handler.get_session")
    with (
        patch("curator.app.handler.update_preset", return_value=mock_preset),
        patch("curator.app.handler.get_presets_for_handler", return_value=[]),
    ):
        handler = Handler(mock_user, mock_sender, MagicMock())

        await handler.save_preset(data)

        # verify no error was raised
        assert True


@pytest.mark.asyncio
async def test_save_preset_with_preset_id_updates_not_creates(
    mock_user, mock_sender, patch_get_session
):
    """Test save_preset with preset_id updates not creates."""
    data = SavePresetData(
        preset_id=1,
        title="Updated",
        title_template="Template",
        labels=None,
        categories=None,
        exclude_from_date_category=False,
        is_default=False,
        handler="mapillary",
    )

    mock_preset = MagicMock(spec=Preset)

    patch_get_session("curator.app.handler.get_session")
    with (
        patch("curator.app.handler.update_preset", return_value=mock_preset) as mock_update,
        patch("curator.app.handler.create_preset") as mock_create,
        patch("curator.app.handler.get_presets_for_handler", return_value=[]),
    ):
        handler = Handler(mock_user, mock_sender, MagicMock())

        await handler.save_preset(data)

        # verify update_preset was called, not create_preset
        mock_update.assert_called_once()
        mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_delete_preset_deletes_preset(mock_user, mock_sender, patch_get_session):
    """Test delete_preset deletes preset successfully."""
    # mock preset
    preset = MagicMock(spec=Preset)
    preset.id = 1
    preset.userid = "user123"
    preset.handler = "mapillary"

    mock_session = MagicMock()
    mock_session.get.return_value = preset

    with (
        patch("curator.app.handler.get_session", return_value=mock_session),
        patch("curator.app.handler.delete_preset", return_value=True),
        patch("curator.app.handler.get_presets_for_handler", return_value=[]),
    ):
        handler = Handler(mock_user, mock_sender, MagicMock())

        # should not raise any exception
        await handler.delete_preset(1)


@pytest.mark.asyncio
async def test_delete_preset_sends_error_for_not_found(
    mock_user, mock_sender, patch_get_session
):
    """Test delete_preset sends error for not found."""
    mock_session = MagicMock()
    mock_session.get.return_value = None

    patch_get_session("curator.app.handler.get_session")
    with patch("curator.app.handler.get_session", return_value=mock_session):
        handler = Handler(mock_user, mock_sender, MagicMock())

        await handler.delete_preset(1)

        # verify error was sent
        mock_sender.send_error.assert_called_once()


@pytest.mark.asyncio
async def test_delete_preset_sends_error_for_wrong_user(
    mock_user, mock_sender, patch_get_session
):
    """Test delete_preset sends error for wrong user."""
    # mock preset with different userid
    preset = MagicMock(spec=Preset)
    preset.id = 1
    preset.userid = "other_user"
    preset.handler = "mapillary"

    mock_session = MagicMock()
    mock_session.get.return_value = preset

    patch_get_session("curator.app.handler.get_session")
    with patch("curator.app.handler.get_session", return_value=mock_session):
        handler = Handler(mock_user, mock_sender, MagicMock())

        await handler.delete_preset(1)

        # verify error was sent
        mock_sender.send_error.assert_called_once()

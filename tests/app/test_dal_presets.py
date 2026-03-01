"""Unit tests for preset DAL functions."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from curator.app.dal import (
    count_all_presets,
    create_preset,
    delete_preset,
    get_all_presets,
    get_default_preset,
    get_presets_for_handler,
    update_preset,
)
from curator.app.models import Preset
from curator.asyncapi import Label


@pytest.fixture
def mock_preset():
    """Standard mock preset object."""
    preset = MagicMock(spec=Preset)
    preset.id = 1
    preset.userid = "user123"
    preset.handler = "mapillary"
    preset.title = "Test Preset"
    preset.title_template = "{{location}} - {{date}}"
    preset.labels = {"language": "en", "value": "Test"}
    preset.categories = "Test, Category"
    preset.exclude_from_date_category = False
    preset.is_default = False
    preset.created_at = datetime.now()
    preset.updated_at = datetime.now()
    return preset


def test_get_all_presets_returns_all_presets(mock_session):
    """Test get_all_presets returns presets across all users."""
    preset1 = MagicMock(spec=Preset)
    preset1.userid = "user1"
    preset2 = MagicMock(spec=Preset)
    preset2.userid = "user2"

    mock_session.exec.return_value.all.return_value = [preset1, preset2]

    result = get_all_presets(mock_session)

    assert result == [preset1, preset2]
    mock_session.exec.assert_called_once()


def test_get_all_presets_returns_empty_list_when_none(mock_session):
    """Test get_all_presets returns empty list when no presets exist."""
    mock_session.exec.return_value.all.return_value = []

    result = get_all_presets(mock_session)

    assert result == []


def test_get_all_presets_passes_offset_and_limit(mock_session):
    """Test get_all_presets passes offset and limit for pagination."""
    mock_session.exec.return_value.all.return_value = []

    get_all_presets(mock_session, offset=50, limit=25)

    mock_session.exec.assert_called_once()


def test_count_all_presets_returns_total(mock_session):
    """Test count_all_presets returns total count across all users."""
    mock_session.exec.return_value.one.return_value = 42

    result = count_all_presets(mock_session)

    assert result == 42
    mock_session.exec.assert_called_once()


def test_count_all_presets_returns_zero_when_empty(mock_session):
    """Test count_all_presets returns zero when no presets exist."""
    mock_session.exec.return_value.one.return_value = 0

    result = count_all_presets(mock_session)

    assert result == 0


def test_get_presets_for_handler_returns_user_presets_ordered(mock_session):
    """Test get_presets_for_handler returns user presets ordered by created_at desc."""
    preset1 = MagicMock(spec=Preset)
    preset1.created_at = datetime(2023, 1, 1)
    preset2 = MagicMock(spec=Preset)
    preset2.created_at = datetime(2023, 1, 2)
    preset3 = MagicMock(spec=Preset)
    preset3.created_at = datetime(2023, 1, 3)

    mock_session.exec.return_value.all.return_value = [preset3, preset2, preset1]

    result = get_presets_for_handler(mock_session, "user123", "mapillary")

    assert result == [preset3, preset2, preset1]
    mock_session.exec.assert_called_once()


def test_get_default_preset_returns_default_when_exists(mock_session):
    """Test get_default_preset returns default when exists."""
    preset = MagicMock(spec=Preset)
    mock_session.exec.return_value.first.return_value = preset

    result = get_default_preset(mock_session, "user123", "mapillary")

    assert result == preset
    mock_session.exec.assert_called_once()


def test_get_default_preset_returns_none_when_no_default(mock_session):
    """Test get_default_preset returns None when no default."""
    mock_session.exec.return_value.first.return_value = None

    result = get_default_preset(mock_session, "user123", "mapillary")

    assert result is None


def test_create_preset_without_default_calls_add_and_flush(mock_session):
    """Test create_preset without default calls add and flush."""
    mock_session.add = MagicMock()
    mock_session.flush = MagicMock()

    result = create_preset(
        session=mock_session,
        userid="user123",
        handler="mapillary",
        title="New Preset",
        title_template="{{location}}",
        labels=None,
        categories=None,
        exclude_from_date_category=False,
        is_default=False,
    )

    assert result is not None
    assert isinstance(result, Preset)
    mock_session.exec.assert_not_called()
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()


def test_update_preset_updates_values_correctly(mock_session, mock_preset):
    """Test update_preset updates values correctly."""
    mock_session.get.return_value = mock_preset
    mock_session.exec.return_value = None

    result = update_preset(
        session=mock_session,
        preset_id=1,
        userid="user123",
        title="Updated Title",
        title_template="Updated Template",
        labels=Label(language="en", value="Updated"),
        categories="Updated",
        exclude_from_date_category=True,
        is_default=True,
    )

    assert result == mock_preset
    assert mock_preset.title == "Updated Title"
    assert mock_preset.title_template == "Updated Template"
    assert mock_preset.labels == Label(language="en", value="Updated")
    assert mock_preset.categories == "Updated"
    assert mock_preset.exclude_from_date_category is True
    assert mock_preset.is_default is True


def test_update_preset_sets_default_clears_others(mock_session, mock_preset):
    """Test update_preset sets default clears others."""
    mock_session.get.return_value = mock_preset
    mock_session.exec.return_value = None

    result = update_preset(
        session=mock_session,
        preset_id=1,
        userid="user123",
        title="Title",
        title_template="Template",
        labels=None,
        categories=None,
        exclude_from_date_category=False,
        is_default=True,
    )

    assert result == mock_preset
    mock_session.exec.assert_called_once()


def test_update_preset_returns_none_for_wrong_user(mock_session, mock_preset):
    """Test update_preset returns None for wrong user."""
    mock_preset.userid = "other_user"
    mock_session.get.return_value = mock_preset

    result = update_preset(
        session=mock_session,
        preset_id=1,
        userid="user123",
        title="Title",
        title_template="Template",
        labels=None,
        categories=None,
        exclude_from_date_category=False,
        is_default=False,
    )

    assert result is None


def test_update_preset_returns_none_for_not_found(mock_session):
    """Test update_preset returns None when preset not found."""
    mock_session.get.return_value = None

    result = update_preset(
        session=mock_session,
        preset_id=1,
        userid="user123",
        title="Title",
        title_template="Template",
        labels=None,
        categories=None,
        exclude_from_date_category=False,
        is_default=False,
    )

    assert result is None


def test_delete_preset_deletes_owned_preset(mock_session, mock_preset):
    """Test delete_preset deletes owned preset."""
    mock_session.get.return_value = mock_preset

    result = delete_preset(mock_session, 1, "user123")

    assert result is True
    mock_session.delete.assert_called_once_with(mock_preset)
    mock_session.flush.assert_called_once()


def test_delete_preset_returns_false_for_wrong_user(mock_session, mock_preset):
    """Test delete_preset returns False for wrong user."""
    mock_preset.userid = "other_user"
    mock_session.get.return_value = mock_preset

    result = delete_preset(mock_session, 1, "user123")

    assert result is False
    mock_session.delete.assert_not_called()


def test_delete_preset_returns_false_for_not_found(mock_session):
    """Test delete_preset returns False when preset not found."""
    mock_session.get.return_value = None

    result = delete_preset(mock_session, 1, "user123")

    assert result is False
    mock_session.delete.assert_not_called()

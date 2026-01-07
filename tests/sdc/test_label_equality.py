"""
Tests for label equality checking in duplicate upload handling.
"""

import json
from pathlib import Path

from curator.asyncapi import Label
from curator.workers.ingest import _are_labels_equal


def load_fixture(filename: str) -> dict:
    """Load a JSON fixture file"""
    fixture_path = Path(__file__).parent / "fixtures" / filename
    with open(fixture_path) as f:
        return json.load(f)


def test_labels_equal_both_none():
    """Test that two None labels are equal"""
    assert _are_labels_equal(None, None) is True


def test_labels_equal_one_none():
    """Test that None and non-None labels are not equal"""
    label = Label(language="en", value="Test")
    assert _are_labels_equal(None, label) is False
    assert _are_labels_equal(label, None) is False


def test_labels_equal_identical():
    """Test that identical labels are equal"""
    label1 = Label(language="en", value="Photo from Mapillary")
    label2 = Label(language="en", value="Photo from Mapillary")
    assert _are_labels_equal(label1, label2) is True


def test_labels_equal_different():
    """Test that different labels are not equal"""
    label1 = Label(language="en", value="Photo from Mapillary")
    label2 = Label(language="en", value="Different Label")
    assert _are_labels_equal(label1, label2) is False


def test_labels_equal_from_production_fixture():
    """
    Test label equality using production fixture data
    """
    fixture = load_fixture("production_sdc.json")
    entity = fixture["entities"]["M176058819"]

    # Get labels from fixture and convert to Label model
    labels_data = entity.get("labels", {})
    production_label = Label.model_validate(labels_data["en"])

    # Create identical label
    identical_label = Label(language="en", value="Photo from Mapillary")

    # Should be equal
    assert _are_labels_equal(production_label, identical_label) is True


def test_labels_not_equal_different_languages():
    """Test that labels with different languages are not equal"""
    label1 = Label(language="en", value="Photo from Mapillary")
    label2 = Label(language="es", value="Foto de Mapillary")
    assert _are_labels_equal(label1, label2) is False

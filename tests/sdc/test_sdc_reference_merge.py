"""Tests for reference merging."""

from curator.app.sdc_merge import (
    merge_references,
)
from curator.asyncapi import (
    Reference,
    StringDataValue,
    StringValueSnak,
    UrlDataValue,
    UrlValueSnak,
)


def make_string_snak(prop: str, value: str, hash: str | None = None) -> StringValueSnak:
    """Helper to create a string value snak."""
    return StringValueSnak(
        property=prop, datavalue=StringDataValue(value=value), hash=hash
    )


def make_url_snak(prop: str, value: str, hash: str | None = None) -> UrlValueSnak:
    """Helper to create a URL value snak."""
    return UrlValueSnak(property=prop, datavalue=UrlDataValue(value=value), hash=hash)


def test_merge_references_no_existing_references():
    """Test merging references when existing is empty."""
    existing = []
    new = [
        Reference(
            snaks={"P813": [make_string_snak("P813", "2024-01-01")]},
            snaks_order=["P813"],
        )
    ]
    merged = merge_references(existing, new)
    assert len(merged) == 1


def test_merge_references_adds_new_references():
    """Test that new references are added."""
    existing = [
        Reference(
            snaks={"P813": [make_string_snak("P813", "2024-01-01")]},
            snaks_order=["P813"],
        )
    ]
    new = [
        Reference(
            snaks={"P854": [make_url_snak("P854", "https://example.com")]},
            snaks_order=["P854"],
        )
    ]
    merged = merge_references(existing, new)
    assert len(merged) == 2


def test_merge_references_no_duplicates():
    """Test that duplicate references are not added."""
    ref = Reference(
        snaks={"P813": [make_string_snak("P813", "2024-01-01")]},
        snaks_order=["P813"],
    )
    existing = [ref]
    new = [ref]
    merged = merge_references(existing, new)
    assert len(merged) == 1

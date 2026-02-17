"""Tests for qualifier merging."""

from curator.app.sdc_merge import (
    Qualifiers,
    merge_qualifiers,
)
from curator.asyncapi import (
    StringDataValue,
    StringValueSnak,
    UrlDataValue,
    UrlValueSnak,
)

# Test helpers


def make_string_snak(prop: str, value: str, hash: str | None = None) -> StringValueSnak:
    """Helper to create a string value snak."""
    return StringValueSnak(
        property=prop, datavalue=StringDataValue(value=value), hash=hash
    )


def make_url_snak(prop: str, value: str, hash: str | None = None) -> UrlValueSnak:
    """Helper to create a URL value snak."""
    return UrlValueSnak(property=prop, datavalue=UrlDataValue(value=value), hash=hash)


# Qualifier merge tests


def test_merge_qualifiers_empty_existing():
    """Test merging qualifiers when existing is empty."""
    existing: Qualifiers = {}
    existing_order: list[str] = []
    new = [make_string_snak("P2093", "alice")]
    merged, merged_order = merge_qualifiers(existing, existing_order, new)
    assert "P2093" in merged
    assert len(merged["P2093"]) == 1
    assert isinstance(merged["P2093"][0], StringValueSnak)
    snak = merged["P2093"][0]
    assert snak.datavalue.value == "alice"
    assert merged_order == ["P2093"]


def test_merge_qualifiers_add_new_property():
    """Test merging qualifiers adds new property."""
    existing: Qualifiers = {"P2093": [make_string_snak("P2093", "alice")]}
    existing_order = ["P2093"]
    new = [make_url_snak("P2699", "https://example.com/alice")]
    merged, merged_order = merge_qualifiers(existing, existing_order, new)
    assert "P2093" in merged
    assert "P2699" in merged
    assert len(merged["P2093"]) == 1
    assert len(merged["P2699"]) == 1
    assert merged_order == ["P2093", "P2699"]


def test_merge_qualifiers_existing_same_values():
    """Test that existing qualifiers with same value are not duplicated."""
    existing: Qualifiers = {"P2093": [make_string_snak("P2093", "alice")]}
    existing_order = ["P2093"]
    new = [make_string_snak("P2093", "alice")]
    merged, merged_order = merge_qualifiers(existing, existing_order, new)
    assert len(merged["P2093"]) == 1
    assert merged_order == ["P2093"]


def test_merge_qualifiers_preserves_order():
    """Test that qualifier order is preserved."""
    existing: Qualifiers = {"P2093": [make_string_snak("P2093", "alice")]}
    existing_order = ["P2093"]
    new = [make_url_snak("P2699", "https://example.com/alice")]
    merged, order = merge_qualifiers(existing, existing_order, new)
    assert order == ["P2093", "P2699"]

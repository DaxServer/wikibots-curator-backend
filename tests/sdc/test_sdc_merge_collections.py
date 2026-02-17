"""Tests for SDC statement collection merging."""

from curator.app.sdc_merge import merge_sdc_statements
from curator.asyncapi import (
    DataValueEntityId,
    EntityIdDataValue,
    EntityIdValueSnak,
    ExternalIdValueSnak,
    Rank,
    Statement,
    StringDataValue,
    StringValueSnak,
    UrlDataValue,
    UrlValueSnak,
    WikibaseEntityType,
)

# Test helpers


def make_entity_id_snak(
    prop: str, numeric_id: int, hash: str | None = None
) -> EntityIdValueSnak:
    """Helper to create an entity ID value snak."""
    return EntityIdValueSnak(
        property=prop,
        datavalue=EntityIdDataValue(
            value=DataValueEntityId.model_validate(
                {"entity-type": WikibaseEntityType.ITEM, "numeric-id": numeric_id}
            )
        ),
        hash=hash,
    )


def make_string_snak(prop: str, value: str, hash: str | None = None) -> StringValueSnak:
    """Helper to create a string value snak."""
    return StringValueSnak(
        property=prop, datavalue=StringDataValue(value=value), hash=hash
    )


def make_url_snak(prop: str, value: str, hash: str | None = None) -> UrlValueSnak:
    """Helper to create a URL value snak."""
    return UrlValueSnak(property=prop, datavalue=UrlDataValue(value=value), hash=hash)


def make_external_id_snak(
    prop: str, value: str, hash: str | None = None
) -> ExternalIdValueSnak:
    """Helper to create an external ID value snak."""
    return ExternalIdValueSnak(
        property=prop, datavalue=StringDataValue(value=value), hash=hash
    )


def make_statement(
    mainsnak,
    qualifiers: list | None = None,
    references: list | None = None,
    id: str | None = None,
) -> Statement:
    """Helper to create a statement."""
    stmt = Statement(mainsnak=mainsnak, rank=Rank.NORMAL, id=id)
    if qualifiers:
        grouped = {}
        order = []
        for snak in qualifiers:
            prop = snak.property
            if prop not in grouped:
                grouped[prop] = []
                order.append(prop)
            grouped[prop].append(snak)
        stmt.qualifiers = grouped
        stmt.qualifiers_order = order
    if references:
        stmt.references = references
    return stmt


# SDC-level merge tests


def test_merge_sdc_statements_add_new_properties():
    """Test merging new properties into existing SDC."""
    existing = [make_statement(make_entity_id_snak("P170", 123))]
    new = [make_statement(make_external_id_snak("P1947", "photo123"))]
    merged = merge_sdc_statements(existing, new)
    assert len(merged) == 2


def test_merge_sdc_statements_merge_existing():
    """Test merging statements for existing property."""
    existing = [
        make_statement(
            make_entity_id_snak("P170", 123),
            qualifiers=[make_string_snak("P2093", "alice")],
        )
    ]
    new = [
        make_statement(
            make_entity_id_snak("P170", 123),
            qualifiers=[make_url_snak("P2699", "https://example.com/alice")],
        )
    ]
    merged = merge_sdc_statements(existing, new)
    assert len(merged) == 1
    assert "P2093" in merged[0].qualifiers
    assert "P2699" in merged[0].qualifiers


def test_merge_sdc_statements_complex_scenario():
    """Test complex merge with multiple properties and statements."""
    existing = [
        make_statement(make_entity_id_snak("P170", 123)),
        make_statement(make_external_id_snak("P1947", "photo123")),
    ]
    new = [
        make_statement(
            make_entity_id_snak("P170", 123),
            qualifiers=[make_string_snak("P2093", "alice")],
        ),
        make_statement(make_entity_id_snak("P571", 456)),
    ]
    merged = merge_sdc_statements(existing, new)
    assert len(merged) == 3


def test_merge_sdc_statements_preserves_all_existing():
    """Test that all existing statements are preserved when no merge needed."""
    existing = [
        make_statement(make_entity_id_snak("P170", 123)),
        make_statement(make_external_id_snak("P1947", "photo123")),
    ]
    new = [make_statement(make_entity_id_snak("P571", 456))]
    merged = merge_sdc_statements(existing, new)
    assert len(merged) == 3


def test_merge_sdc_statements_empty_existing():
    """Test merging when existing is empty."""
    existing = []
    new = [make_statement(make_entity_id_snak("P170", 123))]
    merged = merge_sdc_statements(existing, new)
    assert len(merged) == 1


def test_merge_sdc_statements_empty_new():
    """Test merging when new is empty."""
    existing = [make_statement(make_entity_id_snak("P170", 123))]
    new = []
    merged = merge_sdc_statements(existing, new)
    assert len(merged) == 1

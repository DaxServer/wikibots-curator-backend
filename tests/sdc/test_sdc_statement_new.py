"""Tests for statement merging with new properties."""

from curator.app.sdc_merge import safe_merge_statement
from curator.asyncapi import (
    DataValueEntityId,
    EntityIdDataValue,
    EntityIdValueSnak,
    Rank,
    Statement,
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


# Statement merge tests


def test_safe_merge_statement_new_property():
    """Test merging when there are no existing statements for the property."""
    existing = []
    new = make_statement(make_entity_id_snak("P170", 123))
    merged = safe_merge_statement(existing, new)
    assert len(merged) == 1
    assert merged[0].mainsnak.property == "P170"


def test_safe_merge_statement_existing_different_value():
    """Test that new statement with different value is not added when exists."""
    existing = [make_statement(make_entity_id_snak("P170", 123))]
    new = make_statement(make_entity_id_snak("P170", 456))
    merged = safe_merge_statement(existing, new)
    assert len(merged) == 1  # Keep existing, don't add new

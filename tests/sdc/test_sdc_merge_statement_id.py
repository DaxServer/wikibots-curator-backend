"""Tests for statement ID and hash preservation."""

from curator.app.sdc_merge import safe_merge_statement
from curator.asyncapi import (
    DataValueEntityId,
    EntityIdDataValue,
    EntityIdValueSnak,
    Rank,
    SomeValueSnak,
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


def make_some_value_snak(prop: str, hash: str | None = None) -> SomeValueSnak:
    """Helper to create a some value snak."""
    return SomeValueSnak(property=prop, hash=hash)


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


# CRITICAL TESTS: Verify statement id and hash preservation


def test_merge_preserves_statement_id():
    """Test CRITICAL: Statement id is preserved during merge.

    Without the statement id, Wikimedia Commons would create a duplicate
    instead of updating the existing statement.
    """
    existing = make_statement(
        make_some_value_snak("P170", hash="existing_mainsnak_hash"),
        id="M123$EXISTING_STATEMENT_ID",
    )
    new = make_statement(make_some_value_snak("P170"))

    merged = safe_merge_statement([existing], new)

    assert len(merged) == 1
    assert merged[0].id == "M123$EXISTING_STATEMENT_ID", (
        "Statement id MUST be preserved for Commons to update the correct statement"
    )


def test_merge_preserves_mainsnak_hash():
    """Test CRITICAL: Mainsnak hash is preserved during merge.

    Without the hash, Wikimedia Commons cannot identify which snak to update.
    """
    existing = make_statement(
        make_some_value_snak("P170", hash="abc123hash"),
        id="M123$ID",
    )
    new = make_statement(make_some_value_snak("P170"))

    merged = safe_merge_statement([existing], new)

    assert len(merged) == 1
    assert merged[0].mainsnak.hash == "abc123hash", (
        "Mainsnak hash MUST be preserved for Commons to identify the snak"
    )


def test_merge_creates_new_object_not_in_place():
    """Test that merge creates a new Statement object only when changes are made.

    This ensures that when nothing changes (same qualifiers and references),
    the original object is preserved to avoid unnecessary updates.
    """
    existing = make_statement(
        make_some_value_snak("P170", hash="original_hash"),
        id="M123$ORIGINAL",
    )
    new = make_statement(make_some_value_snak("P170"))

    merged = safe_merge_statement([existing], new)

    # When nothing changed, the original object should be preserved
    assert merged[0] is existing, (
        "Should preserve original Statement object when nothing changed"
    )

    # Fields should be the same
    assert merged[0].id == existing.id
    assert merged[0].mainsnak.hash == existing.mainsnak.hash

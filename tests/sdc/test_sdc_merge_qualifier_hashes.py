"""Tests for qualifier hash preservation."""

from curator.app.sdc_merge import safe_merge_statement
from curator.asyncapi import (
    DataValueEntityId,
    DataValueQuantity,
    EntityIdDataValue,
    EntityIdValueSnak,
    ExternalIdValueSnak,
    QuantityDataValue,
    QuantityValueSnak,
    Rank,
    Reference,
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


def make_external_id_snak(
    prop: str, value: str, hash: str | None = None
) -> ExternalIdValueSnak:
    """Helper to create an external ID value snak."""
    return ExternalIdValueSnak(
        property=prop, datavalue=StringDataValue(value=value), hash=hash
    )


def make_quantity_snak(prop: str, amount: float, unit_id: str) -> QuantityValueSnak:
    """Helper to create a quantity value snak."""
    return QuantityValueSnak(
        property=prop,
        datavalue=QuantityDataValue(
            value=DataValueQuantity(
                amount=f"+{amount}",
                upper_bound=None,
                lower_bound=None,
                unit=f"http://www.wikidata.org/entity/{unit_id}",
            )
        ),
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


# CRITICAL TESTS: Verify qualifier hash preservation


def test_merge_preserves_qualifier_hashes():
    """Test CRITICAL: Qualifier hashes are preserved during merge.

    When merging new qualifiers, existing qualifiers must keep their hashes.
    """
    existing_qualifier = make_string_snak("P2093", "alice", hash="qualifier_hash_456")
    existing = make_statement(
        make_some_value_snak("P170", hash="mainsnak_hash"),
        qualifiers=[existing_qualifier],
        id="M123$ID",
    )
    new_qualifier = make_url_snak("P2699", "https://example.com/alice")
    new = make_statement(make_some_value_snak("P170"), qualifiers=[new_qualifier])

    merged = safe_merge_statement([existing], new)

    assert len(merged) == 1
    assert "P2093" in merged[0].qualifiers
    assert merged[0].qualifiers["P2093"][0].hash == "qualifier_hash_456", (
        "Existing qualifier hash MUST be preserved"
    )

    # New qualifier should not have a hash
    assert "P2699" in merged[0].qualifiers
    assert merged[0].qualifiers["P2699"][0].hash is None, (
        "New qualifier should not have a hash"
    )


def test_merge_preserves_all_identifiers_comprehensive():
    """Test CRITICAL: All identifiers (id and all hashes) are preserved.

    This is a comprehensive test that verifies the complete fix for the
    bug where identifiers were lost during merge.
    """
    existing = make_statement(
        mainsnak=make_some_value_snak("P170", hash="mainsnak_hash_123"),
        qualifiers=[
            make_string_snak("P2093", "alice", hash="qualifier1_hash"),
            make_url_snak("P2699", "https://old.com", hash="qualifier2_hash"),
        ],
        references=[
            Reference(
                snaks={"P854": [make_url_snak("P854", "https://ref.com")]},
                snaks_order=["P854"],
                hash="reference_hash",
            )
        ],
        id="M456$STATEMENT_ID",
    )

    new = make_statement(
        mainsnak=make_some_value_snak("P170"),
        qualifiers=[
            make_string_snak("P2093", "alice"),  # Same value, no hash
            make_string_snak("P1476", "New Title"),  # New qualifier
        ],
    )

    merged = safe_merge_statement([existing], new)

    # CRITICAL ASSERTIONS
    assert merged[0].id == "M456$STATEMENT_ID", "Statement id must be preserved"
    assert merged[0].mainsnak.hash == "mainsnak_hash_123", (
        "Mainsnak hash must be preserved"
    )

    # Check qualifiers
    assert "P2093" in merged[0].qualifiers
    assert merged[0].qualifiers["P2093"][0].hash == "qualifier1_hash", (
        "Existing qualifier hash must be preserved"
    )

    assert "P2699" in merged[0].qualifiers
    assert merged[0].qualifiers["P2699"][0].hash == "qualifier2_hash", (
        "Existing qualifier hash must be preserved"
    )

    assert "P1476" in merged[0].qualifiers
    assert merged[0].qualifiers["P1476"][0].hash is None, (
        "New qualifier should not have a hash"
    )

    # Check references
    assert len(merged[0].references) == 1
    assert merged[0].references[0].hash == "reference_hash", (
        "Reference hash must be preserved"
    )

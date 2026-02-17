"""Tests for statement merging with existing properties."""

from curator.app.sdc_merge import safe_merge_statement
from curator.asyncapi import (
    DataValueEntityId,
    DataValueQuantity,
    EntityIdDataValue,
    EntityIdValueSnak,
    QuantityDataValue,
    QuantityValueSnak,
    Rank,
    Reference,
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


# Statement merge tests


def test_safe_merge_statement_same_value_add_qualifiers():
    """Test merging qualifiers when mainsnak values match."""
    existing = make_statement(
        make_entity_id_snak("P170", 123),
        qualifiers=[make_string_snak("P2093", "alice")],
    )
    new = make_statement(
        make_entity_id_snak("P170", 123),
        qualifiers=[make_url_snak("P2699", "https://example.com/alice")],
    )
    merged = safe_merge_statement([existing], new)
    assert len(merged) == 1
    assert "P2093" in merged[0].qualifiers
    assert "P2699" in merged[0].qualifiers


def test_safe_merge_statement_same_value_add_references():
    """Test merging references when mainsnak values match."""
    existing = make_statement(
        make_entity_id_snak("P170", 123),
        references=[
            Reference(
                snaks={"P813": [make_string_snak("P813", "2024-01-01")]},
                snaks_order=["P813"],
            )
        ],
    )
    new = make_statement(
        make_entity_id_snak("P170", 123),
        references=[
            Reference(
                snaks={"P854": [make_url_snak("P854", "https://example.com")]},
                snaks_order=["P854"],
            )
        ],
    )
    merged = safe_merge_statement([existing], new)
    assert len(merged) == 1
    assert len(merged[0].references) == 2


def test_safe_merge_statement_same_value_add_both():
    """Test merging both qualifiers and references."""
    existing = make_statement(
        make_entity_id_snak("P170", 123),
        qualifiers=[make_string_snak("P2093", "alice")],
        references=[
            Reference(
                snaks={"P813": [make_string_snak("P813", "2024-01-01")]},
                snaks_order=["P813"],
            )
        ],
    )
    new = make_statement(
        make_entity_id_snak("P170", 123),
        qualifiers=[make_url_snak("P2699", "https://example.com/alice")],
        references=[
            Reference(
                snaks={"P854": [make_url_snak("P854", "https://example.com")]},
                snaks_order=["P854"],
            )
        ],
    )
    merged = safe_merge_statement([existing], new)
    assert len(merged) == 1
    assert "P2093" in merged[0].qualifiers
    assert "P2699" in merged[0].qualifiers
    assert len(merged[0].references) == 2


def test_safe_merge_statement_multiple_existing_preserves_first():
    """Test that when multiple existing statements, first is preserved."""
    existing = [
        make_statement(make_entity_id_snak("P170", 123)),
        make_statement(make_entity_id_snak("P170", 456)),
    ]
    new = make_statement(make_entity_id_snak("P170", 123))
    merged = safe_merge_statement(existing, new)
    assert len(merged) == 2


def test_safe_merge_statement_same_mainsnak_different_qualifiers():
    """Test merging adds new qualifiers when mainsnak matches."""
    existing = make_statement(
        make_entity_id_snak("P170", 123),
        qualifiers=[make_string_snak("P2093", "alice")],
    )
    new = make_statement(
        make_entity_id_snak("P170", 123),
        qualifiers=[make_string_snak("P2093", "bob")],
    )
    merged = safe_merge_statement([existing], new)
    assert len(merged) == 1
    assert len(merged[0].qualifiers["P2093"]) == 2

"""Tests for production SDC fixture parsing."""

import json
from pathlib import Path

from curator.asyncapi import (
    DataValueEntityId,
    DataValueQuantity,
    EntityIdDataValue,
    EntityIdValueSnak,
    ExternalIdValueSnak,
    QuantityDataValue,
    QuantityValueSnak,
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


# Production fixture tests


def test_production_fixture_parsing():
    """Test that production SDC data can be parsed correctly."""
    fixture_path = Path(__file__).parent / "fixtures" / "production_sdc.json"
    with open(fixture_path) as f:
        production_data = json.load(f)

    entity = production_data["entities"]["M176058819"]
    statements_data = entity["statements"]

    statements = []
    for prop, stmt_list in statements_data.items():
        for stmt_data in stmt_list:
            stmt = Statement.model_validate(stmt_data)
            statements.append(stmt)

    assert len(statements) == 13
    properties = {s.mainsnak.property for s in statements}
    assert "P170" in properties
    assert "P1947" in properties
    assert "P6216" in properties
    assert "P275" in properties

    p170_stmt = next(s for s in statements if s.mainsnak.property == "P170")
    assert p170_stmt.id is not None
    assert p170_stmt.id.startswith("M176058819$")
    assert p170_stmt.mainsnak.hash is not None
    assert "P2093" in p170_stmt.qualifiers
    assert "P13988" in p170_stmt.qualifiers

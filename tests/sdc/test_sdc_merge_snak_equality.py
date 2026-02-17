"""Tests for snak equality in SDC merge operations."""

from curator.app.sdc_merge import (
    are_snaks_equal,
)
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


# Snak equality tests


def test_are_snaks_equal_entity_id():
    """Test snak equality for entity ID values."""
    snak1 = make_entity_id_snak("P170", 123)
    snak2 = make_entity_id_snak("P170", 123)
    assert are_snaks_equal(snak1, snak2)


def test_are_snaks_equal_string():
    """Test snak equality for string values."""
    snak1 = make_string_snak("P2093", "alice")
    snak2 = make_string_snak("P2093", "alice")
    assert are_snaks_equal(snak1, snak2)


def test_are_snaks_equal_external_id():
    """Test snak equality for external ID values."""
    snak1 = make_external_id_snak("P1947", "photo123")
    snak2 = make_external_id_snak("P1947", "photo123")
    assert are_snaks_equal(snak1, snak2)


def test_are_snaks_equal_quantity():
    """Test snak equality for quantity values."""
    snak1 = make_quantity_snak("P2048", 2988, "Q355198")
    snak2 = make_quantity_snak("P2048", 2988, "Q355198")
    assert are_snaks_equal(snak1, snak2)


def test_are_snaks_equal_different_types():
    """Test that snaks of different types are not equal."""
    snak1 = make_entity_id_snak("P170", 123)
    snak2 = make_string_snak("P170", "123")
    assert not are_snaks_equal(snak1, snak2)


def test_are_snaks_equal_different_properties():
    """Test that snaks with different properties are not equal."""
    snak1 = make_entity_id_snak("P170", 123)
    snak2 = make_entity_id_snak("P571", 123)
    assert not are_snaks_equal(snak1, snak2)

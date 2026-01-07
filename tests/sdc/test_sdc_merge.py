import json
from pathlib import Path

from curator.app.sdc_merge import (
    Qualifiers,
    are_snaks_equal,
    merge_qualifiers,
    merge_references,
    merge_sdc_statements,
    safe_merge_statement,
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


# Qualifier merge tests


def test_merge_qualifiers_empty_existing():
    """Test merging qualifiers when existing is empty."""
    existing: Qualifiers = {}
    new = [make_string_snak("P2093", "alice")]
    merged, _ = merge_qualifiers(existing, new)
    assert "P2093" in merged
    assert len(merged["P2093"]) == 1
    assert isinstance(merged["P2093"][0], StringValueSnak)
    snak = merged["P2093"][0]
    assert snak.datavalue.value == "alice"


def test_merge_qualifiers_add_new_property():
    """Test merging qualifiers adds new property."""
    existing: Qualifiers = {"P2093": [make_string_snak("P2093", "alice")]}
    new = [make_url_snak("P2699", "https://example.com/alice")]
    merged, _ = merge_qualifiers(existing, new)
    assert "P2093" in merged
    assert "P2699" in merged
    assert len(merged["P2093"]) == 1
    assert len(merged["P2699"]) == 1


def test_merge_qualifiers_existing_same_values():
    """Test that existing qualifiers with same value are not duplicated."""
    existing: Qualifiers = {"P2093": [make_string_snak("P2093", "alice")]}
    new = [make_string_snak("P2093", "alice")]
    merged, _ = merge_qualifiers(existing, new)
    assert len(merged["P2093"]) == 1


def test_merge_qualifiers_preserves_order():
    """Test that qualifier order is preserved."""
    existing: Qualifiers = {"P2093": [make_string_snak("P2093", "alice")]}
    new = [make_url_snak("P2699", "https://example.com/alice")]
    merged, order = merge_qualifiers(existing, new, return_order=True)  # type: ignore
    assert order == ["P2093", "P2699"]


# Reference merge tests


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
    assert (
        merged[0].id == "M123$EXISTING_STATEMENT_ID"
    ), "Statement id MUST be preserved for Commons to update the correct statement"


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
    assert (
        merged[0].mainsnak.hash == "abc123hash"
    ), "Mainsnak hash MUST be preserved for Commons to identify the snak"


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
    assert (
        merged[0].qualifiers["P2093"][0].hash == "qualifier_hash_456"
    ), "Existing qualifier hash MUST be preserved"

    # New qualifier should not have a hash
    assert "P2699" in merged[0].qualifiers
    assert (
        merged[0].qualifiers["P2699"][0].hash is None
    ), "New qualifier should not have a hash"


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
    assert (
        merged[0].mainsnak.hash == "mainsnak_hash_123"
    ), "Mainsnak hash must be preserved"

    # Check qualifiers
    assert "P2093" in merged[0].qualifiers
    assert (
        merged[0].qualifiers["P2093"][0].hash == "qualifier1_hash"
    ), "Existing qualifier hash must be preserved"

    assert "P2699" in merged[0].qualifiers
    assert (
        merged[0].qualifiers["P2699"][0].hash == "qualifier2_hash"
    ), "Existing qualifier hash must be preserved"

    assert "P1476" in merged[0].qualifiers
    assert (
        merged[0].qualifiers["P1476"][0].hash is None
    ), "New qualifier should not have a hash"

    # Check references
    assert len(merged[0].references) == 1
    assert (
        merged[0].references[0].hash == "reference_hash"
    ), "Reference hash must be preserved"


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
    assert (
        merged[0] is existing
    ), "Should preserve original Statement object when nothing changed"

    # Fields should be the same
    assert merged[0].id == existing.id
    assert merged[0].mainsnak.hash == existing.mainsnak.hash


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


def test_production_merge_preserves_hash_fields():
    """Test that merge preserves hash fields from production data."""
    fixture_path = Path(__file__).parent / "fixtures" / "production_sdc.json"
    with open(fixture_path) as f:
        production_data = json.load(f)

    entity = production_data["entities"]["M176058819"]
    statements_data = entity["statements"]

    existing_statements = []
    for prop, stmt_list in statements_data.items():
        for stmt_data in stmt_list:
            stmt = Statement.model_validate(stmt_data)
            existing_statements.append(stmt)

    merged = merge_sdc_statements(existing_statements, existing_statements)

    for merged_stmt in merged:
        prop = merged_stmt.mainsnak.property
        orig_stmt = next(s for s in existing_statements if s.mainsnak.property == prop)

        orig_hash = orig_stmt.mainsnak.hash
        merged_hash = merged_stmt.mainsnak.hash
        assert merged_hash == orig_hash, f"Hash not preserved for {prop}"

        orig_id = orig_stmt.id
        merged_id = merged_stmt.id
        assert merged_id == orig_id, f"ID not preserved for {prop}"


def test_production_fixture_statement_serialization():
    """Test that production statements can be serialized back to JSON."""
    fixture_path = Path(__file__).parent / "fixtures" / "production_sdc.json"
    with open(fixture_path) as f:
        production_data = json.load(f)

    entity = production_data["entities"]["M176058819"]
    statements_data = entity["statements"]

    for prop, stmt_list in statements_data.items():
        for stmt_data in stmt_list:
            stmt = Statement.model_validate(stmt_data)
            serialized = stmt.model_dump(mode="json", by_alias=True, exclude_none=True)

            assert (
                serialized["mainsnak"]["property"] == stmt_data["mainsnak"]["property"]
            )
            assert serialized["rank"] == stmt_data["rank"]

            if "id" in stmt_data:
                assert serialized.get("id") == stmt_data["id"]

            if "hash" in stmt_data["mainsnak"]:
                assert (
                    serialized["mainsnak"].get("hash") == stmt_data["mainsnak"]["hash"]
                )

            if "qualifiers" in stmt_data:
                assert serialized.get("qualifiers") is not None
                for qprop in stmt_data["qualifiers"]:
                    assert qprop in serialized["qualifiers"]

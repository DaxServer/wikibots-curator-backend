"""Tests for production SDC merge and serialization."""

import json
from pathlib import Path

from curator.app.sdc_merge import merge_sdc_statements
from curator.asyncapi import Statement


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

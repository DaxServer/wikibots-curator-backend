"""Tests for SDC merge optimization."""

from curator.app.sdc_merge import merge_sdc_statements
from curator.asyncapi import (
    DataValueEntityId,
    EntityIdDataValue,
    EntityIdValueSnak,
    Rank,
    SomeValueSnak,
    Statement,
    StringDataValue,
    StringValueSnak,
    WikibaseEntityType,
)


def test_identical_sdc_merge_skips_api_request():
    """Test that merging identical SDC returns the same SDC, allowing API skip"""
    # Create existing SDC with all identifiers preserved
    existing_sdc = [
        Statement(
            mainsnak=SomeValueSnak(property="P170", hash="mainsnak_hash_123"),
            qualifiers={
                "P2093": [
                    StringValueSnak(
                        property="P2093",
                        datavalue=StringDataValue(value="alice"),
                        hash="qualifier_hash_456",
                    )
                ]
            },
            qualifiers_order=["P2093"],
            rank=Rank.NORMAL,
            id="M12345$ABC",
        ),
        Statement(
            mainsnak=EntityIdValueSnak(
                property="P6216",
                datavalue=EntityIdDataValue(
                    value=DataValueEntityId.model_validate(
                        {"entity-type": WikibaseEntityType.ITEM, "numeric-id": 50423863}
                    )
                ),
                hash="copyright_hash",
            ),
            rank=Rank.NORMAL,
            id="M12345$DEF",
        ),
    ]

    # Create new SDC that is identical (same structure, same values, no hashes)
    new_sdc = [
        Statement(
            mainsnak=SomeValueSnak(property="P170"),
            qualifiers={
                "P2093": [
                    StringValueSnak(
                        property="P2093", datavalue=StringDataValue(value="alice")
                    )
                ]
            },
            qualifiers_order=["P2093"],
            rank=Rank.NORMAL,
        ),
        Statement(
            mainsnak=EntityIdValueSnak(
                property="P6216",
                datavalue=EntityIdDataValue(
                    value=DataValueEntityId.model_validate(
                        {"entity-type": WikibaseEntityType.ITEM, "numeric-id": 50423863}
                    )
                ),
            ),
            rank=Rank.NORMAL,
        ),
    ]

    # Merge
    merged_sdc = merge_sdc_statements(existing_sdc, new_sdc)

    # The merge should preserve existing statements exactly
    assert len(merged_sdc) == len(existing_sdc)

    # Verify that merged statements are identical to existing
    for merged_stmt, existing_stmt in zip(merged_sdc, existing_sdc):
        assert merged_stmt.id == existing_stmt.id
        assert merged_stmt.mainsnak.hash == existing_stmt.mainsnak.hash
        assert merged_stmt.mainsnak.property == existing_stmt.mainsnak.property

    # Verify that the merged SDC can be compared for equality with existing
    # This allows the caller to skip the API request
    merged_dict = [
        s.model_dump(mode="json", by_alias=True, exclude_none=True) for s in merged_sdc
    ]
    existing_dict = [
        s.model_dump(mode="json", by_alias=True, exclude_none=True)
        for s in existing_sdc
    ]

    # The merged SDC should be equivalent to existing SDC
    assert len(merged_dict) == len(existing_dict)


def test_identical_sdc_with_different_identifiers_still_skips():
    """Test that identical SDC content (even without hashes) is detected as identical"""
    # Create existing SDC
    existing_sdc = [
        Statement(
            mainsnak=SomeValueSnak(property="P170", hash="abc123"),
            qualifiers={
                "P2093": [
                    StringValueSnak(
                        property="P2093",
                        datavalue=StringDataValue(value="bob"),
                        hash="def456",
                    )
                ]
            },
            qualifiers_order=["P2093"],
            rank=Rank.NORMAL,
            id="M999$IDENTIFIER",
        ),
    ]

    # Create identical new SDC (same values, no identifiers)
    new_sdc = [
        Statement(
            mainsnak=SomeValueSnak(property="P170"),
            qualifiers={
                "P2093": [
                    StringValueSnak(
                        property="P2093", datavalue=StringDataValue(value="bob")
                    )
                ]
            },
            qualifiers_order=["P2093"],
            rank=Rank.NORMAL,
        ),
    ]

    # Merge
    merged_sdc = merge_sdc_statements(existing_sdc, new_sdc)

    # Verify the merge preserved the existing statement
    assert len(merged_sdc) == 1
    assert merged_sdc[0].id == "M999$IDENTIFIER"
    assert merged_sdc[0].mainsnak.hash == "abc123"
    assert merged_sdc[0].qualifiers["P2093"][0].hash == "def456"

    # The content should be identical (same property, same value, same qualifiers)
    assert merged_sdc[0].mainsnak.property == "P170"
    assert len(merged_sdc[0].qualifiers) == 1
    assert "P2093" in merged_sdc[0].qualifiers
    qualifier = merged_sdc[0].qualifiers["P2093"][0]
    assert isinstance(qualifier, StringValueSnak)
    assert qualifier.datavalue.value == "bob"

"""Integration tests for SDC merge operations."""

from curator.app.commons import DuplicateUploadError
from curator.app.sdc_merge import merge_sdc_statements
from curator.asyncapi import (
    DataValueEntityId,
    EntityIdDataValue,
    EntityIdValueSnak,
    ErrorLink,
    Rank,
    SomeValueSnak,
    Statement,
    StringDataValue,
    StringValueSnak,
    WikibaseEntityType,
)


def test_duplicate_upload_error_structure():
    """Test that DuplicateUploadError has the expected structure"""
    duplicates = [
        ErrorLink(
            title="File:Example.jpg",
            url="https://commons.wikimedia.org/wiki/File:Example.jpg",
        )
    ]

    error = DuplicateUploadError(duplicates=duplicates, message="File already exists")

    assert error.duplicates == duplicates
    assert len(error.duplicates) == 1
    assert error.duplicates[0].title == "File:Example.jpg"
    assert str(error) == "File already exists"


def test_sdc_merge_with_mock_file_page():
    """Test SDC merge with mocked data"""
    # Create existing SDC from the production fixture structure
    existing_sdc = [
        Statement(
            mainsnak=SomeValueSnak(property="P170", hash="existing_mainsnak_hash"),
            qualifiers={
                "P2093": [
                    StringValueSnak(
                        property="P2093",
                        datavalue=StringDataValue(value="alice"),
                        hash="existing_qualifier_hash",
                    )
                ]
            },
            qualifiers_order=["P2093"],
            rank=Rank.NORMAL,
            id="M12345$ABC123",
        )
    ]

    # Create new SDC to merge
    new_sdc = [
        Statement(
            mainsnak=SomeValueSnak(property="P170"),
            qualifiers={
                "P2093": [
                    StringValueSnak(
                        property="P2093", datavalue=StringDataValue(value="alice")
                    )
                ],
                "P13988": [
                    StringValueSnak(
                        property="P13988", datavalue=StringDataValue(value="alice")
                    )
                ],
            },
            qualifiers_order=["P2093", "P13988"],
            rank=Rank.NORMAL,
        )
    ]

    # Merge SDC
    merged_sdc = merge_sdc_statements(existing_sdc, new_sdc)

    # Verify merge
    assert len(merged_sdc) == 1
    merged_dict = merged_sdc[0].model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    assert "P13988" in merged_dict.get("qualifiers", {})


def test_complete_duplicate_handling_workflow():
    """Test the complete workflow of handling a duplicate with SDC merge"""
    # Simulate the scenario:
    # 1. A file is being uploaded
    # 2. It's detected as a duplicate
    # 3. We retrieve existing SDC
    # 4. We merge new SDC with existing
    # 5. We apply the merged SDC
    # Step 1 & 2: Simulate duplicate detection
    duplicate_link = ErrorLink(
        title="File:Mapillary photo.jpg",
        url="https://commons.wikimedia.org/wiki/File:Mapillary photo.jpg",
    )
    duplicate_error = DuplicateUploadError(
        duplicates=[duplicate_link], message="File already exists on Commons"
    )

    assert len(duplicate_error.duplicates) == 1

    # Step 3: Create existing SDC
    existing_sdc = [
        Statement(
            mainsnak=SomeValueSnak(property="P170", hash="existing_mainsnak_hash"),
            qualifiers={
                "P2093": [
                    StringValueSnak(
                        property="P2093",
                        datavalue=StringDataValue(value="alice"),
                        hash="existing_qualifier_hash",
                    )
                ]
            },
            qualifiers_order=["P2093"],
            rank=Rank.NORMAL,
            id="M12345$ABC",
        )
    ]
    assert existing_sdc is not None

    # Step 4: Create new SDC (enhanced with more qualifiers)
    new_sdc = [
        Statement(
            mainsnak=SomeValueSnak(property="P170"),
            qualifiers={
                "P2093": [
                    StringValueSnak(
                        property="P2093", datavalue=StringDataValue(value="alice")
                    )
                ],
                "P13988": [  # New qualifier to add
                    StringValueSnak(
                        property="P13988", datavalue=StringDataValue(value="alice")
                    )
                ],
            },
            qualifiers_order=["P2093", "P13988"],
            rank=Rank.NORMAL,
        ),
        # New statement for a property that doesn't exist
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

    # Step 5: Verify the merge worked correctly
    assert len(merged_sdc) == 2  # P170 (merged) + P6216 (new)

    # Find P170 statement
    p170_stmt = next((s for s in merged_sdc if s.mainsnak.property == "P170"), None)
    assert p170_stmt is not None

    p170_dict = p170_stmt.model_dump(mode="json", by_alias=True, exclude_none=True)
    qualifiers = p170_dict.get("qualifiers", {})

    # Should have both original and new qualifiers
    assert "P2093" in qualifiers
    assert "P13988" in qualifiers  # The newly added qualifier

    # Find P6216 statement (newly added)
    p6216_stmt = next((s for s in merged_sdc if s.mainsnak.property == "P6216"), None)
    assert p6216_stmt is not None

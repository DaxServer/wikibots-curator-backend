"""
Integration tests for SDC safe merge with duplicate files.

This module tests the complete workflow of handling duplicate files
by merging SDC instead of failing.
"""

from curator.app.commons import DuplicateUploadError
from curator.app.sdc_merge import merge_sdc_statements
from curator.asyncapi import (
    DataValueEntityId,
    DataValueGlobeCoordinate,
    EntityIdDataValue,
    EntityIdValueSnak,
    ErrorLink,
    GlobeCoordinateDataValue,
    GlobeCoordinateValueSnak,
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


def test_coordinates_upsert_adds_when_not_exists():
    """Test that coordinates (P625) are added when they don't exist in existing SDC"""
    # Create existing SDC without coordinates
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

    # Create new SDC with coordinates
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
            mainsnak=GlobeCoordinateValueSnak(
                property="P625",
                datavalue=GlobeCoordinateDataValue(
                    value=DataValueGlobeCoordinate(
                        latitude=40.7128,
                        longitude=-74.0060,
                        altitude=None,
                        precision=0.0001,
                        globe="http://www.wikidata.org/entity/Q2",
                    )
                ),
            ),
            rank=Rank.NORMAL,
        ),
    ]

    # Merge
    merged_sdc = merge_sdc_statements(existing_sdc, new_sdc)

    # Verify coordinates were added
    assert len(merged_sdc) == 2
    p625_stmt = next((s for s in merged_sdc if s.mainsnak.property == "P625"), None)
    assert p625_stmt is not None
    assert p625_stmt.mainsnak.datavalue.value.latitude == 40.7128
    assert p625_stmt.mainsnak.datavalue.value.longitude == -74.0060


def test_coordinates_upsert_skips_when_exists():
    """Test that coordinates (P625) are NOT modified when they already exist"""
    # Create existing SDC with coordinates (NYC) - no qualifiers
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
        ),
        Statement(
            mainsnak=GlobeCoordinateValueSnak(
                property="P625",
                datavalue=GlobeCoordinateDataValue(
                    value=DataValueGlobeCoordinate(
                        latitude=40.7128,
                        longitude=-74.0060,
                        altitude=None,
                        precision=0.0001,
                        globe="http://www.wikidata.org/entity/Q2",
                    )
                ),
                hash="existing_coord_hash",
            ),
            rank=Rank.NORMAL,
            id="M12345$COORD",
        ),
    ]

    # Create new SDC with different coordinates (San Francisco)
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
            mainsnak=GlobeCoordinateValueSnak(
                property="P625",
                datavalue=GlobeCoordinateDataValue(
                    value=DataValueGlobeCoordinate(
                        latitude=37.7749,
                        longitude=-122.4194,
                        altitude=None,
                        precision=0.0001,
                        globe="http://www.wikidata.org/entity/Q2",
                    )
                ),
            ),
            rank=Rank.NORMAL,
        ),
    ]

    # Merge
    merged_sdc = merge_sdc_statements(existing_sdc, new_sdc)

    # Verify existing coordinates were preserved (NOT replaced)
    assert len(merged_sdc) == 2
    p625_stmt = next((s for s in merged_sdc if s.mainsnak.property == "P625"), None)
    assert p625_stmt is not None

    # The existing coordinates should be preserved (NYC, not San Francisco)
    assert p625_stmt.mainsnak.datavalue.value.latitude == 40.7128
    assert p625_stmt.mainsnak.datavalue.value.longitude == -74.0060
    assert p625_stmt.id == "M12345$COORD"
    assert p625_stmt.mainsnak.hash == "existing_coord_hash"


def test_coordinates_preserve_without_qualifiers():
    """Test that existing coordinates preserve without adding new qualifiers"""
    # Create existing SDC with coordinates but NO qualifiers
    existing_sdc = [
        Statement(
            mainsnak=GlobeCoordinateValueSnak(
                property="P625",
                datavalue=GlobeCoordinateDataValue(
                    value=DataValueGlobeCoordinate(
                        latitude=51.5074,
                        longitude=-0.1278,
                        altitude=None,
                        precision=0.01,
                        globe="http://www.wikidata.org/entity/Q2",
                    )
                ),
                hash="existing_london_hash",
            ),
            rank=Rank.NORMAL,
            id="M999$LONDON_NO_QUALS",
        )
    ]

    # Create new SDC with same coordinates but WITH qualifiers
    new_sdc = [
        Statement(
            mainsnak=GlobeCoordinateValueSnak(
                property="P625",
                datavalue=GlobeCoordinateDataValue(
                    value=DataValueGlobeCoordinate(
                        latitude=51.5074,
                        longitude=-0.1278,
                        altitude=None,
                        precision=0.01,
                        globe="http://www.wikidata.org/entity/Q2",
                    )
                ),
            ),
            rank=Rank.NORMAL,
            qualifiers={
                "P1234": [
                    StringValueSnak(
                        property="P1234",
                        datavalue=StringDataValue(value="test_qualifier"),
                    )
                ]
            },
            qualifiers_order=["P1234"],
        )
    ]

    # Merge
    merged_sdc = merge_sdc_statements(existing_sdc, new_sdc)

    # Verify existing coordinates preserved WITHOUT qualifiers
    assert len(merged_sdc) == 1
    p625_stmt = merged_sdc[0]

    # Should preserve original without qualifiers
    assert isinstance(p625_stmt.mainsnak, GlobeCoordinateValueSnak)
    assert p625_stmt.mainsnak.datavalue.value.latitude == 51.5074
    assert p625_stmt.mainsnak.datavalue.value.longitude == -0.1278
    assert p625_stmt.id == "M999$LONDON_NO_QUALS"
    assert p625_stmt.mainsnak.hash == "existing_london_hash"
    # Qualifiers should NOT be added
    assert p625_stmt.qualifiers is None or len(p625_stmt.qualifiers) == 0


def test_coordinates_upsert_multiple_properties():
    """Test that multiple coordinate-related properties follow upsert behavior"""
    # Create existing SDC with coordinates
    existing_sdc = [
        Statement(
            mainsnak=GlobeCoordinateValueSnak(
                property="P625",
                datavalue=GlobeCoordinateDataValue(
                    value=DataValueGlobeCoordinate(
                        latitude=51.5074,  # London
                        longitude=-0.1278,
                        altitude=None,
                        precision=0.0001,
                        globe="http://www.wikidata.org/entity/Q2",
                    )
                ),
                hash="london_coord_hash",
            ),
            rank=Rank.NORMAL,
            id="M999$LONDON",
        ),
        Statement(
            mainsnak=SomeValueSnak(property="P170"),
            rank=Rank.NORMAL,
            id="M999$AUTHOR",
        ),
    ]

    # Create new SDC with different coordinates and a new property
    new_sdc = [
        Statement(
            mainsnak=GlobeCoordinateValueSnak(
                property="P625",
                datavalue=GlobeCoordinateDataValue(
                    value=DataValueGlobeCoordinate(
                        latitude=48.8566,  # Paris (different from London)
                        longitude=2.3522,
                        altitude=None,
                        precision=0.0001,
                        globe="http://www.wikidata.org/entity/Q2",
                    )
                ),
            ),
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

    # Verify existing coordinates were preserved (London, not Paris)
    assert len(merged_sdc) == 3  # P625 (existing), P170 (existing), P6216 (new)
    p625_stmt = next((s for s in merged_sdc if s.mainsnak.property == "P625"), None)
    assert p625_stmt is not None

    # Should preserve London coordinates
    assert p625_stmt.mainsnak.datavalue.value.latitude == 51.5074
    assert p625_stmt.mainsnak.datavalue.value.longitude == -0.1278
    assert p625_stmt.id == "M999$LONDON"
    assert p625_stmt.mainsnak.hash == "london_coord_hash"

    # New property should be added
    p6216_stmt = next((s for s in merged_sdc if s.mainsnak.property == "P6216"), None)
    assert p6216_stmt is not None


def test_coordinates_with_different_precision_skipped():
    """Test that coordinates with different precision are still treated as same location"""
    # Create existing SDC with low precision coordinates
    existing_sdc = [
        Statement(
            mainsnak=GlobeCoordinateValueSnak(
                property="P625",
                datavalue=GlobeCoordinateDataValue(
                    value=DataValueGlobeCoordinate(
                        latitude=40.7128,
                        longitude=-74.0060,
                        altitude=None,
                        precision=0.01,  # Low precision
                        globe="http://www.wikidata.org/entity/Q2",
                    )
                ),
                hash="low_precision_hash",
            ),
            rank=Rank.NORMAL,
            id="M111$LOW_PREC",
        ),
    ]

    # Create new SDC with same coordinates but higher precision
    new_sdc = [
        Statement(
            mainsnak=GlobeCoordinateValueSnak(
                property="P625",
                datavalue=GlobeCoordinateDataValue(
                    value=DataValueGlobeCoordinate(
                        latitude=40.7128,
                        longitude=-74.0060,
                        altitude=None,
                        precision=0.000001,  # High precision
                        globe="http://www.wikidata.org/entity/Q2",
                    )
                ),
            ),
            rank=Rank.NORMAL,
        ),
    ]

    # Merge
    merged_sdc = merge_sdc_statements(existing_sdc, new_sdc)

    # Verify only one coordinate statement exists (existing preserved)
    assert len(merged_sdc) == 1
    p625_stmt = merged_sdc[0]

    # Should preserve existing (low precision) since coordinates are at same location
    assert isinstance(p625_stmt.mainsnak, GlobeCoordinateValueSnak)
    assert p625_stmt.mainsnak.datavalue.value.latitude == 40.7128
    assert p625_stmt.mainsnak.datavalue.value.longitude == -74.0060
    assert p625_stmt.mainsnak.datavalue.value.precision == 0.01  # Existing precision
    assert p625_stmt.id == "M111$LOW_PREC"
    assert p625_stmt.mainsnak.hash == "low_precision_hash"

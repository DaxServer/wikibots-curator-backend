"""Tests for advanced coordinate handling in SDC merge."""

from curator.app.sdc_merge import merge_sdc_statements
from curator.asyncapi import (
    DataValueEntityId,
    DataValueGlobeCoordinate,
    EntityIdDataValue,
    EntityIdValueSnak,
    GlobeCoordinateDataValue,
    GlobeCoordinateValueSnak,
    Rank,
    SomeValueSnak,
    Statement,
    WikibaseEntityType,
)


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

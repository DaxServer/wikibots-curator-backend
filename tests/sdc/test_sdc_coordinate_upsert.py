"""Tests for coordinate upsert behavior."""

from curator.app.sdc_merge import merge_sdc_statements
from curator.asyncapi import (
    DataValueGlobeCoordinate,
    GlobeCoordinateDataValue,
    GlobeCoordinateValueSnak,
    Rank,
    SomeValueSnak,
    Statement,
    StringDataValue,
    StringValueSnak,
)


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

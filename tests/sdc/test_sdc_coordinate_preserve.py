"""Tests for coordinate preservation behavior."""

from curator.app.sdc_merge import merge_sdc_statements
from curator.asyncapi import (
    DataValueGlobeCoordinate,
    GlobeCoordinateDataValue,
    GlobeCoordinateValueSnak,
    Rank,
    Statement,
    StringDataValue,
    StringValueSnak,
)


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

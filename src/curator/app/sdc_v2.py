from __future__ import annotations

from datetime import datetime, timezone

from curator.asyncapi import (
    DataValueEntityId,
    DataValueGlobeCoordinate,
    DataValueQuantity,
    DataValueTime,
    EntityIdDataValue,
    EntityIdValueSnak,
    ExternalIdValueSnak,
    GlobeCoordinateDataValue,
    GlobeCoordinateValueSnak,
    NoValueSnak,
    QuantityDataValue,
    QuantityValueSnak,
    Rank,
    SdcV2,
    SomeValueSnak,
    Statement,
    StringDataValue,
    StringValueSnak,
    TimeDataValue,
    TimeValueSnak,
    UrlDataValue,
    UrlValueSnak,
    WikibaseEntityType,
)

type Snak = (
    NoValueSnak
    | SomeValueSnak
    | EntityIdValueSnak
    | ExternalIdValueSnak
    | GlobeCoordinateValueSnak
    | QuantityValueSnak
    | StringValueSnak
    | TimeValueSnak
    | UrlValueSnak
)

type SdcV2Input = dict[str, object]

WIKIDATA_ENTITY = {
    "CCBYSA40": "Q18199165",
    "Copyrighted": "Q50423863",
    "Degree": "Q28390",
    "FileAvailableOnInternet": "Q74228490",
    "Mapillary": "Q17985544",
    "MapillaryDatabase": "Q26757498",
    "Pixel": "Q355198",
}

WIKIDATA_PROPERTY = {
    "AuthorNameString": "P2093",
    "CoordinatesOfThePointOfView": "P1259",
    "CopyrightLicense": "P275",
    "CopyrightStatus": "P6216",
    "Creator": "P170",
    "DescribedAtUrl": "P973",
    "Heading": "P7787",
    "Height": "P2048",
    "Inception": "P571",
    "MapillaryPhotoID": "P1947",
    "MapillaryUsername": "P13988",
    "Operator": "P137",
    "PublishedIn": "P1433",
    "SourceOfFile": "P7482",
    "Width": "P2049",
}


def _get_numeric_id(entity: str) -> int:
    return int(entity[1:])


def _js_number_to_string(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    if value.is_integer():
        return str(int(value))
    return str(value)


def _parse_iso_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.fromisoformat(value)


def _create_string_snak(property_id: str, value: str) -> StringValueSnak:
    return StringValueSnak(property=property_id, datavalue=StringDataValue(value=value))


def _create_url_snak(property_id: str, value: str) -> UrlValueSnak:
    return UrlValueSnak(property=property_id, datavalue=UrlDataValue(value=value))


def _create_some_value_snak(property_id: str) -> SomeValueSnak:
    return SomeValueSnak(property=property_id)


def _create_external_id_snak(property_id: str, value: str) -> ExternalIdValueSnak:
    return ExternalIdValueSnak(
        property=property_id, datavalue=StringDataValue(value=value)
    )


def _create_wikibase_item_snak(property_id: str, item_id: str) -> EntityIdValueSnak:
    return EntityIdValueSnak(
        property=property_id,
        datavalue=EntityIdDataValue(
            value=DataValueEntityId.model_validate(
                {
                    "entity-type": WikibaseEntityType.ITEM,
                    "numeric-id": _get_numeric_id(item_id),
                }
            )
        ),
    )


def _create_globe_coordinate_snak(
    property_id: str,
    latitude: float,
    longitude: float,
    precision: float = 1.0e-9,
) -> GlobeCoordinateValueSnak:
    return GlobeCoordinateValueSnak(
        property=property_id,
        datavalue=GlobeCoordinateDataValue(
            value=DataValueGlobeCoordinate(
                latitude=latitude,
                longitude=longitude,
                altitude=None,
                precision=precision,
                globe="http://www.wikidata.org/entity/Q2",
            )
        ),
    )


def _create_quantity_snak(
    property_id: str,
    amount: int | float,
    unit_item_id: str,
) -> QuantityValueSnak:
    return QuantityValueSnak(
        property=property_id,
        datavalue=QuantityDataValue(
            value=DataValueQuantity(
                amount=f"+{_js_number_to_string(amount)}",
                upper_bound=None,
                lower_bound=None,
                unit=f"http://www.wikidata.org/entity/{unit_item_id}",
            )
        ),
    )


def _create_time_snak(property_id: str, taken_at: str) -> TimeValueSnak:
    dt = _parse_iso_datetime(taken_at).astimezone(timezone.utc)
    date_string = dt.date().isoformat()
    time_string = f"+0000000{date_string}T00:00:00Z"

    return TimeValueSnak(
        property=property_id,
        datavalue=TimeDataValue(
            value=DataValueTime(
                time=time_string,
                timezone=0,
                before=0,
                after=0,
                precision=11,
                calendarmodel="http://www.wikidata.org/entity/Q1985727",
            )
        ),
    )


def _create_statement(
    mainsnak: Snak,
    qualifiers: list[Snak] | None = None,
) -> Statement:
    statement = Statement(mainsnak=mainsnak, rank=Rank.NORMAL)
    if qualifiers:
        grouped: dict[str, list[Snak]] = {}
        order: list[str] = []
        for snak in qualifiers:
            prop = snak.property
            if prop not in grouped:
                grouped[prop] = []
                order.append(prop)
            grouped[prop].append(snak)
        statement.qualifiers = grouped
        statement.qualifiers_order = order
    return statement


def build_statements_from_sdc_v2(sdc_v2: SdcV2 | SdcV2Input) -> list[Statement]:
    if isinstance(sdc_v2, dict):
        sdc_v2 = SdcV2.model_validate(sdc_v2)
    claims: list[Statement] = []

    claims.append(
        _create_statement(
            _create_some_value_snak(WIKIDATA_PROPERTY["Creator"]),
            [
                _create_string_snak(
                    WIKIDATA_PROPERTY["AuthorNameString"], sdc_v2.creator_username
                ),
                _create_external_id_snak(
                    WIKIDATA_PROPERTY["MapillaryUsername"], sdc_v2.creator_username
                ),
            ],
        )
    )

    claims.append(
        _create_statement(
            _create_external_id_snak(
                WIKIDATA_PROPERTY["MapillaryPhotoID"], sdc_v2.mapillary_image_id
            )
        )
    )

    claims.append(
        _create_statement(
            _create_wikibase_item_snak(
                WIKIDATA_PROPERTY["PublishedIn"], WIKIDATA_ENTITY["MapillaryDatabase"]
            )
        )
    )

    claims.append(
        _create_statement(
            _create_time_snak(WIKIDATA_PROPERTY["Inception"], sdc_v2.taken_at)
        )
    )

    claims.append(
        _create_statement(
            _create_wikibase_item_snak(
                WIKIDATA_PROPERTY["SourceOfFile"],
                WIKIDATA_ENTITY["FileAvailableOnInternet"],
            ),
            [
                _create_wikibase_item_snak(
                    WIKIDATA_PROPERTY["Operator"], WIKIDATA_ENTITY["Mapillary"]
                ),
                _create_url_snak(
                    WIKIDATA_PROPERTY["DescribedAtUrl"], sdc_v2.source_url
                ),
            ],
        )
    )

    claims.append(
        _create_statement(
            _create_globe_coordinate_snak(
                WIKIDATA_PROPERTY["CoordinatesOfThePointOfView"],
                sdc_v2.location.latitude,
                sdc_v2.location.longitude,
            ),
            [
                _create_quantity_snak(
                    WIKIDATA_PROPERTY["Heading"],
                    sdc_v2.location.compass_angle,
                    WIKIDATA_ENTITY["Degree"],
                )
            ],
        )
    )

    if sdc_v2.include_default_copyright:
        claims.append(
            _create_statement(
                _create_wikibase_item_snak(
                    WIKIDATA_PROPERTY["CopyrightStatus"],
                    WIKIDATA_ENTITY["Copyrighted"],
                )
            )
        )
        claims.append(
            _create_statement(
                _create_wikibase_item_snak(
                    WIKIDATA_PROPERTY["CopyrightLicense"], WIKIDATA_ENTITY["CCBYSA40"]
                )
            )
        )

    claims.append(
        _create_statement(
            _create_quantity_snak(
                WIKIDATA_PROPERTY["Width"], sdc_v2.width, WIKIDATA_ENTITY["Pixel"]
            )
        )
    )
    claims.append(
        _create_statement(
            _create_quantity_snak(
                WIKIDATA_PROPERTY["Height"], sdc_v2.height, WIKIDATA_ENTITY["Pixel"]
            )
        )
    )

    return claims

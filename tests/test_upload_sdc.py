import json
from pathlib import Path

from pydantic import TypeAdapter

from curator.app.sdc_v2 import build_statements_from_sdc_v2
from curator.asyncapi import (
    EntityIdValueSnak,
    ExternalIdValueSnak,
    GlobeCoordinateValueSnak,
    NoValueSnak,
    QuantityValueSnak,
    SomeValueSnak,
    Statement,
    StringValueSnak,
    TimeValueSnak,
    Upload,
    UrlValueSnak,
    WikibaseEntityType,
)
from curator.protocol import ClientMessage

adapter = TypeAdapter(ClientMessage)


def validate_sdc(sdc_data, expected_type=None):
    payload = {
        "type": "UPLOAD",
        "data": {
            "items": [
                {
                    "id": "1",
                    "input": "test.jpg",
                    "title": "Test Image",
                    "wikitext": "Some wikitext",
                    "sdc": sdc_data,
                }
            ],
            "handler": "mapillary",
        },
    }
    obj = adapter.validate_python(payload)
    assert isinstance(obj, Upload)
    item = obj.data.items[0]
    assert len(item.sdc) == 1
    statement = item.sdc[0]
    assert isinstance(statement, Statement)
    if expected_type:
        assert isinstance(statement.mainsnak, expected_type)
    return statement


def _load_sdc_claim_fixtures():
    path = Path(__file__).resolve().parent / "fixtures" / "sdc_claims.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_upload_sdc_novalue():
    sdc_data = [
        {
            "mainsnak": {
                "snaktype": "novalue",
                "property": "P180",
            },
            "type": "statement",
            "rank": "normal",
        }
    ]
    statement = validate_sdc(sdc_data, NoValueSnak)
    assert statement.mainsnak.snaktype == "novalue"
    assert statement.mainsnak.property == "P180"


def test_upload_sdc_somevalue():
    sdc_data = [
        {
            "mainsnak": {
                "snaktype": "somevalue",
                "property": "P180",
            },
            "type": "statement",
            "rank": "normal",
        }
    ]
    statement = validate_sdc(sdc_data, SomeValueSnak)
    assert statement.mainsnak.snaktype == "somevalue"
    assert statement.mainsnak.property == "P180"


def test_upload_sdc_entityid():
    sdc_data = [
        {
            "mainsnak": {
                "snaktype": "value",
                "property": "P180",
                "datatype": "wikibase-item",
                "datavalue": {
                    "type": "wikibase-entityid",
                    "value": {"entity-type": "item", "numeric-id": 42},
                },
            },
            "type": "statement",
            "rank": "normal",
        }
    ]
    statement = validate_sdc(sdc_data, EntityIdValueSnak)
    assert statement.mainsnak.datavalue.value.numeric_id == 42
    assert statement.mainsnak.datavalue.value.entity_type == WikibaseEntityType.ITEM


def test_upload_sdc_externalid():
    sdc_data = [
        {
            "mainsnak": {
                "snaktype": "value",
                "property": "P217",
                "datatype": "external-id",
                "datavalue": {
                    "type": "string",
                    "value": "ABC-123",
                },
            },
            "type": "statement",
            "rank": "normal",
        }
    ]
    statement = validate_sdc(sdc_data, ExternalIdValueSnak)
    assert statement.mainsnak.datavalue.value == "ABC-123"


def test_upload_sdc_globecoordinate():
    sdc_data = [
        {
            "mainsnak": {
                "snaktype": "value",
                "property": "P625",
                "datatype": "globe-coordinate",
                "datavalue": {
                    "type": "globecoordinate",
                    "value": {
                        "latitude": 52.5200,
                        "longitude": 13.4050,
                        "altitude": None,
                        "precision": 0.0001,
                        "globe": "http://www.wikidata.org/entity/Q2",
                    },
                },
            },
            "type": "statement",
            "rank": "normal",
        }
    ]
    statement = validate_sdc(sdc_data, GlobeCoordinateValueSnak)
    assert statement.mainsnak.datavalue.value.latitude == 52.5200
    assert statement.mainsnak.datavalue.value.longitude == 13.4050


def test_upload_sdc_quantity():
    sdc_data = [
        {
            "mainsnak": {
                "snaktype": "value",
                "property": "P2043",
                "datatype": "quantity",
                "datavalue": {
                    "type": "quantity",
                    "value": {
                        "amount": "+10.5",
                        "unit": "http://www.wikidata.org/entity/Q11573",
                        "upperBound": "+10.6",
                        "lowerBound": "+10.4",
                    },
                },
            },
            "type": "statement",
            "rank": "normal",
        }
    ]
    statement = validate_sdc(sdc_data, QuantityValueSnak)
    assert statement.mainsnak.datavalue.value.amount == "+10.5"
    assert (
        statement.mainsnak.datavalue.value.unit
        == "http://www.wikidata.org/entity/Q11573"
    )


def test_upload_sdc_string():
    sdc_data = [
        {
            "mainsnak": {
                "snaktype": "value",
                "property": "P1476",
                "datatype": "string",
                "datavalue": {
                    "type": "string",
                    "value": "A beautiful sunset",
                },
            },
            "type": "statement",
            "rank": "normal",
        }
    ]
    statement = validate_sdc(sdc_data, StringValueSnak)
    assert statement.mainsnak.datavalue.value == "A beautiful sunset"


def test_upload_sdc_time():
    sdc_data = [
        {
            "mainsnak": {
                "snaktype": "value",
                "property": "P571",
                "datatype": "time",
                "datavalue": {
                    "type": "time",
                    "value": {
                        "time": "+2023-01-01T00:00:00Z",
                        "timezone": 0,
                        "before": 0,
                        "after": 0,
                        "precision": 11,
                        "calendarmodel": "http://www.wikidata.org/entity/Q1985727",
                    },
                },
            },
            "type": "statement",
            "rank": "normal",
        }
    ]
    statement = validate_sdc(sdc_data, TimeValueSnak)
    assert statement.mainsnak.datavalue.value.time == "+2023-01-01T00:00:00Z"


def test_upload_sdc_url():
    sdc_data = [
        {
            "mainsnak": {
                "snaktype": "value",
                "property": "P854",
                "datatype": "url",
                "datavalue": {
                    "type": "string",
                    "value": "https://example.com",
                },
            },
            "type": "statement",
            "rank": "normal",
        }
    ]
    statement = validate_sdc(sdc_data, UrlValueSnak)
    assert statement.mainsnak.datavalue.value == "https://example.com"


def test_build_statements_from_sdc_v2_matches_v1_fixtures():
    fixtures = _load_sdc_claim_fixtures()
    for fixture in fixtures:
        statements = build_statements_from_sdc_v2(fixture["sdc_v2"])
        dumped = [
            s.model_dump(mode="json", by_alias=True, exclude_none=True)
            for s in statements
        ]
        assert dumped == fixture["claims"]

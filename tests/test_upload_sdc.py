from pydantic import TypeAdapter

from curator.protocol import (
    ClientMessage,
    PatchedUpload,
    PatchedUploadData,
    PatchedUploadItem,
)

adapter = TypeAdapter(ClientMessage)


def test_upload_with_structured_sdc():
    sdc_data = [
        {
            "mainsnak": {
                "snaktype": "value",
                "property": "P180",
                "datavalue": {
                    "value": {"entity-type": "item", "id": "Q42"},
                    "type": "wikibase-entityid",
                },
            },
            "type": "statement",
            "rank": "normal",
        }
    ]
    data = {
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
    obj = adapter.validate_python(data)
    assert isinstance(obj, PatchedUpload)
    assert obj.type == "UPLOAD"
    assert isinstance(obj.data, PatchedUploadData)
    assert len(obj.data.items) == 1
    assert isinstance(obj.data.items[0], PatchedUploadItem)
    assert obj.data.items[0].sdc == sdc_data


def test_upload_with_string_sdc():
    sdc_data = "some string sdc"
    data = {
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
    obj = adapter.validate_python(data)
    assert isinstance(obj, PatchedUpload)
    assert obj.data.items[0].sdc == sdc_data

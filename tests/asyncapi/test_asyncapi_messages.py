import pytest
from pydantic import TypeAdapter, ValidationError

from curator.asyncapi import (
    FetchBatches,
    FetchBatchUploads,
    FetchImages,
    SubscribeBatch,
    Upload,
    UploadData,
    UploadItem,
)
from curator.protocol import ClientMessage

adapter = TypeAdapter(ClientMessage)


def test_fetch_images_payload():
    data = {"type": "FETCH_IMAGES", "data": "Q42", "handler": "mapillary"}
    obj = adapter.validate_python(data)
    assert isinstance(obj, FetchImages)
    assert obj.type == "FETCH_IMAGES"
    assert obj.data == "Q42"
    assert obj.handler.value == "mapillary"


def test_upload_payload():
    data = {
        "type": "UPLOAD",
        "data": {
            "items": [
                {
                    "id": "1",
                    "input": "test.jpg",
                    "title": "Test Image",
                    "wikitext": "Some wikitext",
                    "copyright_override": True,
                }
            ],
            "handler": "mapillary",
        },
    }
    obj = adapter.validate_python(data)
    assert isinstance(obj, Upload)
    assert obj.type == "UPLOAD"
    assert isinstance(obj.data, UploadData)
    assert len(obj.data.items) == 1
    assert isinstance(obj.data.items[0], UploadItem)
    assert obj.data.items[0].id == "1"
    assert obj.data.items[0].copyright_override is True
    assert obj.data.handler == "mapillary"


def test_subscribe_batch_payload():
    data = {"type": "SUBSCRIBE_BATCH", "data": 123}
    obj = adapter.validate_python(data)
    assert isinstance(obj, SubscribeBatch)
    assert obj.type == "SUBSCRIBE_BATCH"
    assert obj.data == 123


def test_fetch_batches_payload():
    data = {
        "type": "FETCH_BATCHES",
        "data": {"page": 1, "limit": 10, "userid": "user123"},
    }
    obj = adapter.validate_python(data)
    assert isinstance(obj, FetchBatches)
    assert obj.type == "FETCH_BATCHES"
    assert obj.data.page == 1
    assert obj.data.limit == 10
    assert obj.data.userid == "user123"


def test_fetch_batch_uploads_payload():
    data = {"type": "FETCH_BATCH_UPLOADS", "data": 456}
    obj = adapter.validate_python(data)
    assert isinstance(obj, FetchBatchUploads)
    assert obj.type == "FETCH_BATCH_UPLOADS"
    assert obj.data == 456


def test_invalid_payload_type():
    data = {"type": "INVALID_TYPE", "data": {}}
    with pytest.raises(ValidationError):  # Pydantic raises ValidationError
        adapter.validate_python(data)


def test_fetch_batches_default_values():
    data = {"type": "FETCH_BATCHES", "data": {}}
    obj = adapter.validate_python(data)
    assert isinstance(obj, FetchBatches)
    assert obj.data.page == 1
    assert obj.data.limit == 100
    assert obj.data.userid is None

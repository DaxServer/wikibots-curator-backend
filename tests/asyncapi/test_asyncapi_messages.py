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
    UploadSlice,
)
from curator.protocol import ClientMessage

adapter = TypeAdapter(ClientMessage)


def test_fetch_images_payload():
    data = {"type": "FETCH_IMAGES", "data": "Q42"}
    obj = adapter.validate_python(data)
    assert isinstance(obj, FetchImages)
    assert obj.type == "FETCH_IMAGES"
    assert obj.data == "Q42"


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
    assert obj.data.handler == "mapillary"


def test_upload_payload_with_sdc_v2():
    data = {
        "type": "UPLOAD",
        "data": {
            "items": [
                {
                    "id": "1",
                    "input": "test.jpg",
                    "title": "Test Image",
                    "wikitext": "Some wikitext",
                    "sdc_v2": {
                        "type": "mapillary",
                        "version": 1,
                        "creator_username": "alice",
                        "mapillary_image_id": "168951548443095",
                        "taken_at": "2023-01-01T00:00:00Z",
                        "source_url": "https://example.com/photo",
                        "location": {
                            "latitude": 52.52,
                            "longitude": 13.405,
                            "compass_angle": 123.45,
                        },
                        "width": 1920,
                        "height": 1080,
                        "include_default_copyright": True,
                    },
                }
            ],
            "handler": "mapillary",
        },
    }
    obj = adapter.validate_python(data)
    assert isinstance(obj, Upload)
    assert isinstance(obj.data, UploadData)
    assert len(obj.data.items) == 1
    assert isinstance(obj.data.items[0], UploadItem)
    assert obj.data.items[0].sdc_v2 is not None
    assert obj.data.items[0].sdc_v2.type == "mapillary"
    assert obj.data.items[0].sdc_v2.version == 1
    assert obj.data.items[0].sdc_v2.creator_username == "alice"


def test_upload_slice_payload_with_sdc_v2():
    data = {
        "type": "UPLOAD_SLICE",
        "data": {
            "batchid": 123,
            "sliceid": 0,
            "handler": "mapillary",
            "items": [
                {
                    "id": "img1",
                    "input": "test",
                    "title": "T",
                    "wikitext": "W",
                    "sdc_v2": {
                        "type": "mapillary",
                        "version": 1,
                        "creator_username": "alice",
                        "mapillary_image_id": "img1",
                        "taken_at": "2023-01-01T00:00:00Z",
                        "source_url": "https://example.com/photo",
                        "location": {
                            "latitude": 52.52,
                            "longitude": 13.405,
                            "compass_angle": 123.45,
                        },
                        "width": 1920,
                        "height": 1080,
                        "include_default_copyright": False,
                    },
                }
            ],
        },
    }
    obj = adapter.validate_python(data)
    assert isinstance(obj, UploadSlice)
    assert obj.data.items[0].sdc_v2 is not None
    assert obj.data.items[0].sdc_v2.mapillary_image_id == "img1"


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

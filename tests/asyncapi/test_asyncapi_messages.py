"""Tests for AsyncAPI message serialization and validation."""

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
    """Test that FETCH_IMAGES message deserializes correctly."""
    data = {"type": "FETCH_IMAGES", "data": "Q42", "handler": "mapillary"}
    obj = adapter.validate_python(data)
    assert isinstance(obj, FetchImages)
    assert obj.type == "FETCH_IMAGES"
    assert obj.data == "Q42"
    assert obj.handler.value == "mapillary"


def test_upload_payload():
    """Test that UPLOAD message deserializes correctly with nested data."""
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
    """Test that SUBSCRIBE_BATCH message deserializes correctly."""
    data = {"type": "SUBSCRIBE_BATCH", "data": 123}
    obj = adapter.validate_python(data)
    assert isinstance(obj, SubscribeBatch)
    assert obj.type == "SUBSCRIBE_BATCH"
    assert obj.data == 123


def test_fetch_batches_payload():
    """Test that FETCH_BATCHES message deserializes correctly with pagination."""
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
    """Test that FETCH_BATCH_UPLOADS message deserializes correctly."""
    data = {"type": "FETCH_BATCH_UPLOADS", "data": 456}
    obj = adapter.validate_python(data)
    assert isinstance(obj, FetchBatchUploads)
    assert obj.type == "FETCH_BATCH_UPLOADS"
    assert obj.data == 456


def test_invalid_payload_type():
    """Test that invalid message type raises ValidationError."""
    data = {"type": "INVALID_TYPE", "data": {}}
    with pytest.raises(ValidationError):  # Pydantic raises ValidationError
        adapter.validate_python(data)


def test_fetch_batches_default_values():
    """Test that FETCH_BATCHES uses default values for optional fields."""
    data = {"type": "FETCH_BATCHES", "data": {}}
    obj = adapter.validate_python(data)
    assert isinstance(obj, FetchBatches)
    assert obj.data.page == 1
    assert obj.data.limit == 100
    assert obj.data.userid is None

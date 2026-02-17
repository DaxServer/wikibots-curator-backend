"""Tests for label serialization in AsyncAPI models."""

from typing import cast
from unittest.mock import patch

from curator.app.dal import create_upload_request
from curator.app.models import UploadItem as ModelUploadItem
from curator.app.models import UploadRequest
from curator.asyncapi import Label
from curator.asyncapi import UploadItem as AsyncUploadItem


def test_create_upload_request_label_serialization(mocker, mock_session):
    """Test that Label objects are serialized to dicts during upload request creation."""
    # Mock create_batch and ensure_user to avoid DB interactions
    with (
        patch("curator.app.dal.ensure_user"),
        patch("curator.app.dal.create_batch") as mock_create_batch,
    ):
        mock_batch = mocker.MagicMock()
        mock_batch.id = 123
        mock_create_batch.return_value = mock_batch

        # Create a Label object (Pydantic model)
        label = Label(language="en", value="Photo from Mapillary")

        # Create an UploadItem with the Label object
        item = AsyncUploadItem(
            id="img1",
            input="test_collection",
            title="Test Title",
            wikitext="Test Wikitext",
            labels=label,
        )

        # Call the function, casting to match the expected type in the app
        reqs = create_upload_request(
            session=mock_session,
            username="testuser",
            userid="user123",
            payload=cast(list[ModelUploadItem], [item]),
            handler="mapillary",
            encrypted_access_token="encrypted_token",
        )

        # Verify
        assert len(reqs) == 1
        req = reqs[0]
        assert isinstance(req, UploadRequest)

        # The key verification: labels should be a dict, not a Label object
        assert isinstance(req.labels, dict)
        assert req.labels == {"language": "en", "value": "Photo from Mapillary"}

"""Tests for core data access layer functions."""

from curator.app.dal import (
    create_upload_requests_for_batch,
    get_batch,
    get_upload_request_by_id,
    reset_failed_uploads_to_new_batch,
    retry_selected_uploads_to_new_batch,
)
from curator.app.models import UploadItem
from curator.asyncapi import Rank, SomeValueSnak, Statement


def test_get_upload_request_by_id(mocker, mock_session):
    """Test that get_upload_request_by_id works with integer ID"""
    # Create a mock UploadRequest
    mock_upload_request = mocker.MagicMock()
    mock_upload_request.id = 123
    mock_upload_request.batchid = 456
    mock_upload_request.filename = "test.jpg"

    # Configure the mock session to return our mock upload request
    mock_result = mocker.MagicMock()
    mock_result.first.return_value = mock_upload_request
    mock_session.exec.return_value = mock_result

    # Execute
    result = get_upload_request_by_id(mock_session, 123)

    # Verify
    assert result == mock_upload_request


def test_get_upload_request_by_id_not_found(mocker, mock_session):
    """Test that get_upload_request_by_id returns None when not found"""
    # Configure the mock session to return None
    mock_result = mocker.MagicMock()
    mock_result.first.return_value = None
    mock_session.exec.return_value = mock_result

    # Execute
    result = get_upload_request_by_id(mock_session, 456)

    # Verify
    assert result is None


def test_get_batch(mocker, mock_session):
    """Test that get_batch works with integer ID"""
    # Create a mock Batch with proper attributes
    mock_batch = mocker.MagicMock()
    mock_batch.id = 789
    mock_batch.userid = "user123"
    mock_batch.name = "Test Batch"
    mock_batch.created_at.isoformat.return_value = "2023-01-01T00:00:00"

    # Create mock user
    mock_user = mocker.MagicMock()
    mock_user.username = "testuser"
    mock_batch.user = mock_user

    # Configure the mock session to return our mock batch
    mock_session.exec.return_value.first.return_value = mock_batch
    mock_session.exec.return_value.all.return_value = []

    # Execute
    result = get_batch(mock_session, 789)

    # Verify
    assert result is not None
    assert result.id == 789
    assert result.userid == "user123"
    assert result.username == "testuser"
    # get_batch calls exec twice - once for batch query, once for stats
    assert mock_session.exec.call_count == 2


def test_get_batch_not_found(mock_session):
    """Test that get_batch returns None when not found"""
    # Configure the mock session to return None
    mock_session.exec.return_value.first.return_value = None

    # Execute
    result = get_batch(mock_session, 999)

    # Verify
    assert result is None
    mock_session.exec.assert_called_once()


def test_create_upload_requests_for_batch_does_not_persist_sdc(mock_session):
    """Test that create_upload_requests_for_batch does not persist SDC data."""
    statement = Statement(mainsnak=SomeValueSnak(property="P170"), rank=Rank.NORMAL)

    item = UploadItem(
        id="img1",
        input="seq1",
        title="Test Image",
        wikitext="Some wikitext",
        copyright_override=True,
        sdc=[statement],
    )

    reqs = create_upload_requests_for_batch(
        session=mock_session,
        userid="user123",
        username="testuser",
        batchid=1,
        payload=[item],
        handler="mapillary",
        encrypted_access_token="encrypted_token",
    )

    assert len(reqs) == 1
    assert reqs[0].copyright_override is True
    assert reqs[0].sdc is not None
    assert len(reqs[0].sdc) == 0

    mock_session.add.assert_called()
    mock_session.flush.assert_called_once()


def test_reset_failed_uploads_to_new_batch_copies_uploads(mocker, mock_session):
    """Test that reset_failed_uploads_to_new_batch creates copies, leaving originals unchanged"""
    mock_batch = mocker.MagicMock()
    mock_batch.id = 123
    mock_batch.userid = "user1"
    mock_session.get.return_value = mock_batch

    mock_failed_upload1 = mocker.MagicMock()
    mock_failed_upload1.id = 1
    mock_failed_upload1.batchid = 123
    mock_failed_upload1.userid = "user1"
    mock_failed_upload1.status = "failed"
    mock_failed_upload1.key = "img_key_1"
    mock_failed_upload1.handler = "mapillary"
    mock_failed_upload1.collection = "seq123"
    mock_failed_upload1.filename = "Test_file_1.jpg"
    mock_failed_upload1.wikitext = "== {{int:filedesc}} =="
    mock_failed_upload1.copyright_override = True
    mock_failed_upload1.sdc = []
    mock_failed_upload1.labels = None
    mock_failed_upload1.error = {"type": "generic_error"}
    mock_failed_upload1.result = "failed result"
    mock_failed_upload1.success = None
    mock_failed_upload1.celery_task_id = "old-task-1"

    mock_failed_upload2 = mocker.MagicMock()
    mock_failed_upload2.id = 2
    mock_failed_upload2.batchid = 123
    mock_failed_upload2.userid = "user1"
    mock_failed_upload2.status = "failed"
    mock_failed_upload2.key = "img_key_2"
    mock_failed_upload2.handler = "flickr"
    mock_failed_upload2.collection = "album456"
    mock_failed_upload2.filename = "Test_file_2.jpg"
    mock_failed_upload2.wikitext = "== {{int:filedesc}} =="
    mock_failed_upload2.copyright_override = False
    mock_failed_upload2.sdc = [{"P170": "creator"}]
    mock_failed_upload2.labels = {"en": "label"}
    mock_failed_upload2.error = {"type": "duplicate_error"}
    mock_failed_upload2.result = None
    mock_failed_upload2.success = None
    mock_failed_upload2.celery_task_id = "old-task-2"

    mock_session.exec.return_value.all.return_value = [
        mock_failed_upload1,
        mock_failed_upload2,
    ]

    created_uploads = []

    def mock_add(obj):
        if hasattr(obj, "key"):
            obj.id = len(created_uploads) + 100
            created_uploads.append(obj)

    def mock_add_all(objs):
        for obj in objs:
            mock_add(obj)

    mock_session.add.side_effect = mock_add
    mock_session.add_all.side_effect = mock_add_all

    new_batch_id = 456

    def mock_create_batch(session, userid, username):
        new_batch = mocker.MagicMock()
        new_batch.id = new_batch_id
        new_batch.edit_group_id = "newbatch12345"
        new_batch.userid = userid
        return new_batch

    mocker.patch("curator.app.dal.create_batch", side_effect=mock_create_batch)
    result = reset_failed_uploads_to_new_batch(
        mock_session, 123, "user1", "new_encrypted_token", "testuser"
    )

    upload_ids, edit_group_id = result
    assert len(upload_ids) == 2
    assert edit_group_id == "newbatch12345"

    assert mock_failed_upload1.status == "failed"
    assert mock_failed_upload1.error == {"type": "generic_error"}
    assert mock_failed_upload1.batchid == 123
    assert mock_failed_upload2.status == "failed"
    assert mock_failed_upload2.batchid == 123

    assert len(created_uploads) == 2
    for new_upload in created_uploads:
        assert new_upload.batchid == new_batch_id
        assert new_upload.status == "queued"
        assert new_upload.error is None
        assert new_upload.result is None
        assert new_upload.success is None
        assert new_upload.access_token == "new_encrypted_token"
        assert new_upload.celery_task_id is None
        assert new_upload.userid == "user1"

    upload1 = created_uploads[0]
    assert upload1.key == "img_key_1"
    assert upload1.handler == "mapillary"
    assert upload1.collection == "seq123"
    assert upload1.filename == "Test_file_1.jpg"
    assert upload1.wikitext == "== {{int:filedesc}} =="
    assert upload1.copyright_override is True
    assert upload1.sdc == []

    upload2 = created_uploads[1]
    assert upload2.key == "img_key_2"
    assert upload2.handler == "flickr"
    assert upload2.collection == "album456"
    assert upload2.filename == "Test_file_2.jpg"
    assert upload2.copyright_override is False
    assert upload2.sdc == [{"P170": "creator"}]
    assert upload2.labels == {"en": "label"}


def test_retry_selected_uploads_to_new_batch_copies_uploads(mocker, mock_session):
    """Test that retry_selected_uploads_to_new_batch creates copies, leaving originals unchanged"""
    mock_upload1 = mocker.MagicMock()
    mock_upload1.id = 1
    mock_upload1.batchid = 100
    mock_upload1.userid = "original_user"
    mock_upload1.status = "failed"
    mock_upload1.key = "img_key_1"
    mock_upload1.handler = "mapillary"
    mock_upload1.collection = "seq123"
    mock_upload1.filename = "Test_file_1.jpg"
    mock_upload1.wikitext = "== wikitext =="
    mock_upload1.copyright_override = True
    mock_upload1.sdc = []
    mock_upload1.labels = None
    mock_upload1.error = {"type": "error"}
    mock_upload1.result = "failed"
    mock_upload1.success = None
    mock_upload1.celery_task_id = "old-task-1"

    mock_upload2 = mocker.MagicMock()
    mock_upload2.id = 2
    mock_upload2.batchid = 200
    mock_upload2.userid = "other_user"
    mock_upload2.status = "failed"
    mock_upload2.key = "img_key_2"
    mock_upload2.handler = "flickr"
    mock_upload2.collection = "album456"
    mock_upload2.filename = "Test_file_2.jpg"
    mock_upload2.wikitext = "== more wikitext =="
    mock_upload2.copyright_override = False
    mock_upload2.sdc = [{"P170": "creator"}]
    mock_upload2.labels = {"en": "label"}
    mock_upload2.error = None
    mock_upload2.result = None
    mock_upload2.success = None
    mock_upload2.celery_task_id = "old-task-2"

    mock_session.exec.return_value.all.return_value = [mock_upload1, mock_upload2]

    created_uploads = []

    def mock_add(obj):
        if hasattr(obj, "key"):
            obj.id = len(created_uploads) + 500
            created_uploads.append(obj)

    def mock_add_all(objs):
        for obj in objs:
            mock_add(obj)

    mock_session.add.side_effect = mock_add
    mock_session.add_all.side_effect = mock_add_all

    new_batch_id = 999

    def mock_create_batch(session, userid, username):
        new_batch = mocker.MagicMock()
        new_batch.id = new_batch_id
        new_batch.edit_group_id = "adminbatch789"
        new_batch.userid = userid
        return new_batch

    mocker.patch("curator.app.dal.create_batch", side_effect=mock_create_batch)
    result = retry_selected_uploads_to_new_batch(
        mock_session,
        [1, 2],
        "admin_encrypted_token",
        "admin_userid",
        "admin_username",
    )

    upload_ids, edit_group_id = result
    assert len(upload_ids) == 2
    assert edit_group_id == "adminbatch789"

    assert mock_upload1.status == "failed"
    assert mock_upload1.batchid == 100
    assert mock_upload1.userid == "original_user"
    assert mock_upload1.error == {"type": "error"}
    assert mock_upload2.status == "failed"
    assert mock_upload2.batchid == 200
    assert mock_upload2.userid == "other_user"

    assert len(created_uploads) == 2
    for new_upload in created_uploads:
        assert new_upload.batchid == new_batch_id
        assert new_upload.userid == "admin_userid"
        assert new_upload.status == "queued"
        assert new_upload.error is None
        assert new_upload.result is None
        assert new_upload.success is None
        assert new_upload.access_token == "admin_encrypted_token"
        assert new_upload.celery_task_id is None

    upload1 = created_uploads[0]
    assert upload1.key == "img_key_1"
    assert upload1.handler == "mapillary"
    assert upload1.filename == "Test_file_1.jpg"
    assert upload1.copyright_override is True

    upload2 = created_uploads[1]
    assert upload2.key == "img_key_2"
    assert upload2.handler == "flickr"
    assert upload2.filename == "Test_file_2.jpg"
    assert upload2.copyright_override is False

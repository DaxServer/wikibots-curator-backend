from datetime import datetime

from curator.app.dal_optimized import (
    count_batches_optimized,
    get_batch_ids_with_recent_changes,
    get_batches_minimal,
    get_batches_optimized,
    get_latest_update_time,
)


def test_count_batches_optimized_basic(mocker, mock_session):
    """Test count_batches_optimized returns correct count"""
    # Mock the exec result - count_batches_optimized uses .one() not .scalar_one()
    mock_result = mocker.MagicMock()
    mock_result.one.return_value = 150
    mock_session.exec.return_value = mock_result

    # Execute
    result = count_batches_optimized(mock_session, userid="user123", filter_text=None)

    # Verify
    assert result == 150
    mock_session.exec.assert_called_once()


def test_count_batches_optimized_with_filter(mock_session, mocker):
    """Test count_batches_optimized with filter text"""
    # Mock the exec result
    mock_result = mocker.MagicMock()
    mock_result.one.return_value = 75
    mock_session.exec.return_value = mock_result

    # Execute
    result = count_batches_optimized(mock_session, userid="user123", filter_text="test")

    # Verify
    assert result == 75
    mock_session.exec.assert_called_once()


def test_count_batches_optimized_zero(mock_session, mocker):
    """Test count_batches_optimized returns zero"""
    # Mock the exec result
    mock_result = mocker.MagicMock()
    mock_result.one.return_value = 0
    mock_session.exec.return_value = mock_result

    # Execute
    result = count_batches_optimized(mock_session, userid="user123", filter_text=None)

    # Verify
    assert result == 0
    mock_session.exec.assert_called_once()


def test_get_batches_optimized_basic(mock_session, mocker):
    """Test get_batches_optimized returns batches correctly"""
    # Create datetime objects for created_at
    created_at1 = datetime(2024, 1, 1, 1, 0, 0)
    created_at2 = datetime(2024, 1, 1, 2, 0, 0)

    # 1. Mock the first call: base_query for batches and usernames
    batch1 = mocker.MagicMock()
    batch1.id = 1
    batch1.created_at = created_at1
    batch1.userid = "user123"

    batch2 = mocker.MagicMock()
    batch2.id = 2
    batch2.created_at = created_at2
    batch2.userid = "user123"

    mock_session.exec.return_value.all.return_value = [
        (batch1, "user1"),
        (batch2, "user2"),
    ]

    # 2. Mock the second call: stats_query for these batches
    # row format: (bid, total, queued, in_progress, completed, failed, duplicate)
    mock_session.execute.return_value.all.return_value = [
        (1, 10, 2, 1, 5, 1, 1),
        (2, 15, 3, 2, 7, 2, 1),
    ]

    # Execute
    result = get_batches_optimized(mock_session, userid="user123", filter_text=None)

    # Verify
    assert len(result) == 2
    assert result[0].id == 1
    assert result[0].username == "user1"
    assert result[0].stats.total == 10
    assert result[1].id == 2
    assert result[1].username == "user2"
    assert result[1].stats.total == 15
    assert mock_session.exec.called
    assert mock_session.execute.called


def test_get_batches_minimal(mock_session, mocker):
    """Test get_batches_minimal returns batches correctly"""
    created_at1 = datetime(2024, 1, 1, 1, 0, 0)

    # 1. Mock the first call: base_query
    batch1 = mocker.MagicMock()
    batch1.id = 1
    batch1.created_at = created_at1
    batch1.userid = "user123"

    mock_session.exec.return_value.all.return_value = [
        (batch1, "user1"),
    ]

    # 2. Mock the second call: stats_query
    mock_session.execute.return_value.all.return_value = [
        (1, 10, 2, 1, 5, 1, 1),
    ]

    # Execute
    result = get_batches_minimal(mock_session, batch_ids=[1])

    # Verify
    assert len(result) == 1
    assert result[0].id == 1
    assert result[0].stats.total == 10
    assert mock_session.exec.called
    assert mock_session.execute.called


def test_get_latest_update_time(mock_session, mocker):
    """Test get_latest_update_time returns the max time"""
    t1 = datetime(2024, 1, 1, 1, 0, 0)
    t2 = datetime(2024, 1, 1, 2, 0, 0)

    # Mock session.exec().one() calls
    mock_result1 = mocker.MagicMock()
    mock_result1.one.return_value = t1
    mock_result2 = mocker.MagicMock()
    mock_result2.one.return_value = t2

    mock_session.exec.side_effect = [mock_result1, mock_result2]

    # Execute
    result = get_latest_update_time(mock_session, userid="user123")

    # Verify
    assert result == t2
    assert mock_session.exec.call_count == 2


def test_get_batch_ids_with_recent_changes(mock_session, mocker):
    """Test get_batch_ids_with_recent_changes returns batch IDs correctly"""
    last_update = datetime(2024, 1, 1, 0, 0, 0)

    # Mock the two calls to session.exec().all()
    # 1. From UploadRequest
    mock_session.exec.return_value.all.side_effect = [
        [(1,), (2,)],  # From UploadRequest
        [(2,), (3,)],  # From Batch
    ]

    # Execute
    result = get_batch_ids_with_recent_changes(
        mock_session, last_update, userid="user123", filter_text="test"
    )

    # Verify
    assert set(result) == {1, 2, 3}
    assert mock_session.exec.call_count == 2

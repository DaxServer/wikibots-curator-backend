from datetime import datetime

from curator.app.dal_optimized import (
    count_batches_optimized,
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

    # Mock the execute result with proper row structure
    mock_result = mocker.MagicMock()
    mock_result.all.return_value = [
        (1, created_at1, "user123", "user1", 10, 2, 1, 5, 1, 1),
        (2, created_at2, "user123", "user2", 15, 3, 2, 7, 2, 1),
    ]
    mock_session.execute.return_value = mock_result

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
    mock_session.execute.assert_called_once()


def test_get_batches_minimal(mock_session, mocker):
    """Test get_batches_minimal returns batches correctly"""
    created_at1 = datetime(2024, 1, 1, 1, 0, 0)

    # Mock the execute result
    mock_result = mocker.MagicMock()
    mock_result.all.return_value = [
        (1, created_at1, "user123", "user1", 10, 2, 1, 5, 1, 1),
    ]
    mock_session.execute.return_value = mock_result

    # Execute
    result = get_batches_minimal(mock_session, batch_ids=[1])

    # Verify
    assert len(result) == 1
    assert result[0].id == 1
    mock_session.execute.assert_called_once()


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

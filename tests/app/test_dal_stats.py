"""Tests for statistics aggregation in data access layer."""

from curator.app.dal import get_batches_stats


def test_get_batches_stats(mocker, mock_session):
    """Test that get_batches_stats returns correct statistics for batches."""
    mock_exec_result = mocker.MagicMock()
    mock_session.exec.return_value = mock_exec_result

    # Mock result: [(batch_id, status, count), ...]
    mock_exec_result.all.return_value = [
        (1, "completed", 5),
        (1, "failed", 2),
        (2, "queued", 10),
    ]

    batch_ids = [1, 2]
    stats = get_batches_stats(mock_session, batch_ids)

    assert stats[1].total == 7
    assert stats[1].completed == 5
    assert stats[1].failed == 2
    assert stats[1].queued == 0

    assert stats[2].total == 10
    assert stats[2].queued == 10
    assert stats[2].completed == 0

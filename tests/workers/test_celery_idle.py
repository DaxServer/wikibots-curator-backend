import os
import signal
from unittest.mock import MagicMock, patch

import pytest

# Need to mock celery before importing the module because it tries to connect/configure
with patch("celery.Celery"):
    from curator.workers.celery import (
        on_worker_ready,
        update_heartbeat,
    )


@pytest.fixture
def mock_heartbeat_file(tmp_path):
    # Patch the HEARTBEAT_FILE in the module to use a temp path
    # We need to patch it where it is used.
    # Since it is a global variable in the module, we can patch it there.
    with patch(
        "curator.workers.celery.HEARTBEAT_FILE", tmp_path / "heartbeat"
    ) as mock_file:
        yield mock_file


def test_idle_monitor_kill_after_timeout(mock_heartbeat_file):
    """Test that the monitor kills the process after timeout."""
    pid = 12345

    # Mock dependencies
    with (
        patch("os.getpid", return_value=pid),
        patch("os.kill") as mock_kill,
        patch("threading.Thread") as mock_thread_cls,
        patch("time.sleep"),
        patch("time.time") as mock_time,
    ):
        # Setup mocks
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        # Initial time
        start_time = 1000.0

        # Run on_worker_ready
        on_worker_ready()

        # Verify thread was started
        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()

        # Get the monitor function
        monitor_func = mock_thread_cls.call_args[1]["target"]

        # Verify file was created
        expected_file = mock_heartbeat_file.with_name(
            f"{mock_heartbeat_file.name}_{pid}"
        )
        assert expected_file.exists()

        # Set file mtime to start_time
        os.utime(expected_file, (start_time, start_time))

        # Set current time to start_time + 4 hours + 1 second
        # The monitor calls time.time()
        mock_time.side_effect = [
            start_time + 4 * 3600 + 1,  # For time.time() inside loop
            start_time + 4 * 3600 + 2,  # subsequent calls
        ]

        # Run monitor function once (it should break loop)
        monitor_func()

        # Verify kill was called
        mock_kill.assert_called_with(pid, signal.SIGTERM)


def test_update_heartbeat(mock_heartbeat_file):
    """Test that task execution updates the heartbeat file."""
    ppid = 54321
    pid = 67890

    with patch("os.getppid", return_value=ppid), patch("os.getpid", return_value=pid):
        # Case 1: Parent file exists (Prefork)
        parent_file = mock_heartbeat_file.with_name(
            f"{mock_heartbeat_file.name}_{ppid}"
        )
        parent_file.touch()

        # Verify touch happens
        update_heartbeat()

        assert parent_file.exists()

        # Case 2: Only PID file exists (Solo)
        parent_file.unlink()
        my_file = mock_heartbeat_file.with_name(f"{mock_heartbeat_file.name}_{pid}")
        my_file.touch()

        update_heartbeat()

        assert my_file.exists()

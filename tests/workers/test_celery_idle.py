"""Tests for Celery worker idle detection."""

import os
import signal
import time
from unittest.mock import MagicMock, patch

import pytest

from curator.app.config import CELERY_MAXIMUM_WAIT_TIME

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
    """Test that the monitor kills the process after timeout"""
    pid = 12345

    # Mock dependencies
    with (
        patch("os.getpid", return_value=pid),
        patch("os.kill") as mock_kill,
        patch("threading.Thread") as mock_thread_cls,
        patch("time.sleep") as mock_sleep,
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

        # Set current time to start_time + CELERY_MAXIMUM_WAIT_TIME * 60 + 1 second
        # The monitor compares time.time() - mtime > CELERY_MAXIMUM_WAIT_TIME * 60
        mock_time.return_value = start_time + (CELERY_MAXIMUM_WAIT_TIME * 60) + 1

        # Configure sleep: first call returns None, second call raises to break loop
        class BreakLoop(Exception):
            pass

        mock_sleep.side_effect = [None, BreakLoop]

        # Run monitor function (will sleep once, check timeout, call kill, break)
        # Then sleep again which raises BreakLoop
        try:
            monitor_func()
        except BreakLoop:
            pass

        # Verify kill was called
        mock_kill.assert_called_with(pid, signal.SIGTERM)


def test_idle_monitor_no_kill_if_active_tasks(mock_heartbeat_file):
    """Test that the monitor does NOT kill if there are active tasks"""
    pid = 12345
    worker_name = "celery@test_worker"

    # Mock dependencies
    with (
        patch("os.getpid", return_value=pid),
        patch("os.kill") as mock_kill,
        patch("threading.Thread") as mock_thread_cls,
        patch("time.sleep") as mock_sleep,
        patch("curator.workers.celery.app") as mock_app,
    ):
        # Setup mocks
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        # Setup inspect mock
        mock_inspector = MagicMock()
        mock_app.control.inspect.return_value = mock_inspector
        mock_inspector.active.return_value = {worker_name: [{"id": "task1"}]}

        # Setup sender mock
        mock_sender = MagicMock()
        mock_sender.hostname = worker_name

        # Run on_worker_ready with sender
        on_worker_ready(sender=mock_sender)

        # Get the monitor function
        monitor_func = mock_thread_cls.call_args[1]["target"]

        # Verify file was created
        expected_file = mock_heartbeat_file.with_name(
            f"{mock_heartbeat_file.name}_{pid}"
        )
        assert expected_file.exists()

        # Set file mtime to old time (5 hours ago)
        old_time = time.time() - (5 * 3600)
        os.utime(expected_file, (old_time, old_time))

        # Verify it is old
        assert time.time() - expected_file.stat().st_mtime > CELERY_MAXIMUM_WAIT_TIME

        # Configure sleep to break loop
        class BreakLoop(Exception):
            pass

        mock_sleep.side_effect = [None, BreakLoop]

        # Run monitor
        try:
            monitor_func()
        except BreakLoop:
            pass

        # Verify kill NOT called
        mock_kill.assert_not_called()

        # Verify file touched (mtime is recent)
        assert time.time() - expected_file.stat().st_mtime < 10


def test_update_heartbeat_updates_mtime(mock_heartbeat_file):
    """Test that update_heartbeat updates the file modification time"""
    pid = 12345

    # Create the heartbeat file
    heartbeat_path = mock_heartbeat_file.with_name(f"{mock_heartbeat_file.name}_{pid}")
    heartbeat_path.touch()

    # Set mtime to the past
    start_time = 1000.0
    os.utime(heartbeat_path, (start_time, start_time))

    # Mock dependencies
    with (
        patch("os.getpid", return_value=pid),
        patch("os.getppid", return_value=99999),  # ensure ppid doesn't match
    ):
        # Verify initial state
        assert heartbeat_path.stat().st_mtime == start_time

        # Call update_heartbeat
        update_heartbeat()

        # Verify mtime changed (should be current time, which is > start_time)
        # Since we didn't mock time.time() or os.utime() inside the function (it uses touch),
        # it will use system time.
        assert heartbeat_path.stat().st_mtime > start_time

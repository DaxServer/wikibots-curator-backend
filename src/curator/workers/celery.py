"""Celery application configuration"""

import logging
import os
import signal
import sys
import tempfile
import threading
import time
from pathlib import Path

from celery import Celery
from celery.signals import (
    task_postrun,
    task_prerun,
    worker_init,
    worker_ready,
    worker_shutdown,
)

from curator.app.config import (
    CELERY_BACKEND_URL,
    CELERY_BROKER_URL,
    CELERY_CONCURRENCY,
    CELERY_MAXIMUM_WAIT_TIME,
    CELERY_TASKS_PER_WORKER,
)

logger = logging.getLogger(__name__)


app = Celery("curator")
app.conf.update(
    broker_url=CELERY_BROKER_URL,
    result_backend=CELERY_BACKEND_URL,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
    result_expires=86400,
    result_extended=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    worker_max_tasks_per_child=CELERY_TASKS_PER_WORKER,
    worker_concurrency=CELERY_CONCURRENCY,
    task_routes={
        "curator.workers.tasks.process_upload": {"queue": "uploads"},
    },
    broker_connection_retry_on_startup=True,
    broker_pool_limit=5,
    worker_ready_timeout=30,
    worker_shutdown_timeout=30,
)

# Import tasks AFTER app is created to avoid circular import
from curator.workers import tasks  # noqa: F401, E402

HEARTBEAT_FILE = Path(tempfile.gettempdir()) / "celery_worker_heartbeat"


@worker_init.connect
def on_worker_init(**kwargs):
    """Configure logging for Celery worker processes."""
    # Suppress httpx INFO logs (HTTP Request messages)
    logging.getLogger("httpx").setLevel(logging.WARNING)


@worker_ready.connect
def on_worker_ready(sender=None, **kwargs):
    pid = os.getpid()
    logger.info(f"[celery] Worker ready - PID: {pid}")

    # Create/Touch the heartbeat file initially
    heartbeat_path = HEARTBEAT_FILE.with_name(f"{HEARTBEAT_FILE.name}_{pid}")
    heartbeat_path.touch()

    worker_hostname = sender.hostname if sender else None
    logger.info(
        f"[celery] Idle monitor started. Heartbeat file: {heartbeat_path}. Worker: {worker_hostname}"
    )

    def monitor():
        while True:
            time.sleep(60)
            try:
                # Check for active tasks using inspection API
                if worker_hostname:
                    inspector = app.control.inspect()
                    active_tasks = inspector.active()
                    if active_tasks and active_tasks.get(worker_hostname):
                        # Worker is busy processing tasks, treat as activity
                        heartbeat_path.touch()

                if not heartbeat_path.exists():
                    heartbeat_path.touch()
                    continue

                mtime = heartbeat_path.stat().st_mtime
                if time.time() - mtime > CELERY_MAXIMUM_WAIT_TIME * 60:
                    logger.warning(
                        f"[celery] Idle timeout of {CELERY_MAXIMUM_WAIT_TIME} minutes reached. Exiting worker {pid}."
                    )
                    os.kill(pid, signal.SIGTERM)
                    break
            except Exception as e:
                logger.error(f"[celery] Idle monitor error: {e}")

    t = threading.Thread(target=monitor, daemon=True)
    t.start()


@task_prerun.connect
@task_postrun.connect
def update_heartbeat(**kwargs):
    """Update heartbeat timestamp before and after task execution."""
    ppid = os.getppid()
    pid = os.getpid()

    # Try PPID first (prefork case - update parent's heartbeat)
    path_ppid = HEARTBEAT_FILE.with_name(f"{HEARTBEAT_FILE.name}_{ppid}")
    if path_ppid.exists():
        path_ppid.touch()
        return

    # Try PID (solo case)
    path_pid = HEARTBEAT_FILE.with_name(f"{HEARTBEAT_FILE.name}_{pid}")
    if path_pid.exists():
        path_pid.touch()


@worker_shutdown.connect
def on_worker_shutdown(**kwargs):
    pid = os.getpid()
    logger.info(f"[celery] Worker shutting down - PID: {pid}")

    heartbeat_path = HEARTBEAT_FILE.with_name(f"{HEARTBEAT_FILE.name}_{pid}")
    try:
        heartbeat_path.unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"[celery] Failed to remove heartbeat file: {e}")


def start():
    if sys.platform == "darwin":
        os.environ.setdefault("NO_PROXY", "*")

    app.worker_main(
        [
            "worker",
            "--queues=uploads",
            "--loglevel=INFO",
            "-E",
        ]
    )


if __name__ == "__main__":
    start()

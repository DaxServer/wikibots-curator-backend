"""Celery application configuration"""

import logging
import multiprocessing
import os
import signal
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import cast

from celery import Celery
from celery.signals import (
    task_postrun,
    task_prerun,
    worker_init,
    worker_ready,
    worker_shutdown,
)

from curator.core.config import (
    CELERY_BACKEND_URL,
    CELERY_BROKER_URL,
    CELERY_CONCURRENCY,
    CELERY_MAXIMUM_WAIT_TIME,
    CELERY_TASKS_PER_WORKER,
    redis_client,
)
from curator.db.dal_uploads import count_active_uploads_for_user
from curator.db.engine import get_session

QUEUE_NORMAL = "uploads-normal"
QUEUE_USER_PREFIX = "uploads-"
ACTIVE_USER_QUEUES_KEY = "curator:active_user_queues"


def register_user_queue(userid: str) -> None:
    """Register per-user upload queue and notify running workers if new."""
    queue_name = f"{QUEUE_USER_PREFIX}{userid}"
    if redis_client.sadd(ACTIVE_USER_QUEUES_KEY, queue_name) == 1:
        app.control.add_consumer(queue_name, reply=False)


def cleanup_user_queue_if_empty(userid: str) -> None:
    """Remove user queue when no active uploads remain."""
    try:
        with get_session() as session:
            if count_active_uploads_for_user(session, userid) == 0:
                queue_name = f"{QUEUE_USER_PREFIX}{userid}"
                redis_client.srem(ACTIVE_USER_QUEUES_KEY, queue_name)
                app.control.cancel_consumer(queue_name, reply=False)
    except Exception:
        logger.exception(f"[celery] Failed to clean up queue for user {userid}")


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
    worker_concurrency=CELERY_CONCURRENCY,
    task_routes={},  # Queues specified dynamically at dispatch time
    broker_connection_retry_on_startup=True,
    broker_pool_limit=5,
    worker_ready_timeout=30,
    worker_shutdown_timeout=300,
    worker_soft_shutdown_timeout=300,
)

# Import tasks AFTER app is created to avoid circular import
from curator.workers import tasks  # noqa: F401, E402

HEARTBEAT_FILE = Path(tempfile.gettempdir()) / "celery_worker_heartbeat"
logger = logging.getLogger(__name__)

# Shared across forked workers
task_counter = multiprocessing.Value("i", 0)


@worker_init.connect
def on_worker_init(**kwargs) -> None:
    """Configure logging on worker startup."""
    logging.getLogger("httpx").setLevel(logging.WARNING)


@task_postrun.connect
def on_task_postrun(task=None, args=None, **kwargs) -> None:
    with task_counter.get_lock():
        task_counter.value += 1
        if task_counter.value == CELERY_TASKS_PER_WORKER:
            logger.info(
                f"Worker reached task limit ({CELERY_TASKS_PER_WORKER}). Initiating shutdown."
            )
            os.kill(os.getppid(), signal.SIGTERM)

    if (
        task
        and task.name == "curator.workers.tasks.process_upload"
        and args
        and len(args) >= 3
    ):
        cleanup_user_queue_if_empty(args[2])


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

    active_user_queues = list(
        cast(set[str], redis_client.smembers(ACTIVE_USER_QUEUES_KEY))
    )
    queues = ",".join([QUEUE_NORMAL] + active_user_queues)

    app.worker_main(
        [
            "worker",
            f"--queues={queues}",
            "--loglevel=INFO",
            "-E",
        ]
    )


if __name__ == "__main__":
    start()

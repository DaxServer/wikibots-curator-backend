"""Celery application configuration."""

import logging
import os
import sys

from celery import Celery
from celery.signals import worker_init, worker_ready, worker_shutdown

from curator.app.db import DB_URL

logger = logging.getLogger(__name__)

# Convert SQLAlchemy URL to Celery-compatible format
# For broker: use sqlalchemy+ prefix with mysql+pymysql (standard)
# For backend: use db+ prefix
CELERY_BROKER_URL = DB_URL.replace(
    "mysql+mysqlconnector://", "sqlalchemy+mysql+pymysql://"
)
CELERY_BACKEND_URL = DB_URL.replace("mysql+mysqlconnector://", "db+mysql+pymysql://")

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
    worker_max_tasks_per_child=100,
    worker_concurrency=1,
    task_routes={
        "curator.workers.tasks.process_upload": {"queue": "uploads"},
    },
    broker_connection_retry_on_startup=True,
    broker_pool_limit=None,
)

# Import tasks AFTER app is created to avoid circular import
from curator.workers import tasks  # noqa: F401, E402


@worker_init.connect
def on_worker_init(**kwargs):
    """Configure logging for Celery worker processes."""
    # Suppress httpx INFO logs (HTTP Request messages)
    logging.getLogger("httpx").setLevel(logging.WARNING)


@worker_ready.connect
def on_worker_ready(**kwargs):
    logger.info(f"[celery] Worker ready - PID: {os.getpid()}")


@worker_shutdown.connect
def on_worker_shutdown(**kwargs):
    logger.info(f"[celery] Worker shutting down - PID: {os.getpid()}")


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

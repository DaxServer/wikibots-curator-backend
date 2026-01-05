"""Celery tasks with exactly-once execution semantics."""

import asyncio
import logging
import os

from curator.workers.celery import app
from curator.workers.ingest import process_one

logger = logging.getLogger(__name__)

# Create a single event loop per worker process
_worker_loop = None


def _get_event_loop():
    """Get or create the worker's event loop."""
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop


@app.task(
    name="curator.workers.tasks.process_upload",
    bind=True,
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def process_upload(self, upload_id: int) -> bool:
    """
    Process a single upload request.

    Exactly-once semantics are handled by process_one() which checks
    if the upload status is 'queued' before processing.
    """
    worker_id = f"{os.getpid()}-{self.request.id}"
    logger.info(f"[celery] [{upload_id}] [{worker_id}] task started")

    loop = _get_event_loop()
    try:
        result = loop.run_until_complete(process_one(upload_id))
        return result
    except Exception as e:
        logger.error(
            f"[celery] [{upload_id}] [{worker_id}] error processing upload: {e}",
            exc_info=True,
        )
        raise
    finally:
        logger.info(f"[celery] [{upload_id}] [{worker_id}] task completed")

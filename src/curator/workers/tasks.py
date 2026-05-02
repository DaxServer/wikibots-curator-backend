"""Celery tasks with exactly-once execution semantics."""

import asyncio
import logging
import os

from celery import Task

from curator.core.errors import HashLockError, SourceCdnError, StorageError
from curator.db.dal_uploads import update_upload_status
from curator.db.engine import get_session
from curator.db.models import UploadStatus
from curator.workers.celery import app
from curator.workers.ingest import process_one

logger = logging.getLogger(__name__)

# Requeue delays in seconds for StorageError retries: 5 min, 10 min, 15 min
STORAGE_ERROR_DELAYS = [300, 600, 900]
# Requeue delays in seconds for HashLockError retries: 1 min each
HASH_LOCK_DELAYS = [60, 60, 60]
# Requeue delay for source CDN 5xx errors: single 10-minute retry
SOURCE_CDN_DELAYS = [600]

# Create a single event loop per worker process
_worker_loop = None


def _get_event_loop():
    """Get or create the worker's event loop."""
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop


def _requeue_or_fail(
    task: Task, upload_id: int, worker_id: str, delays: list[int], exc: Exception
) -> bool:
    """Requeue the task or mark upload as FAILED if retries are exhausted."""
    retry_num = task.request.retries
    if retry_num >= len(delays) or retry_num >= task.max_retries:
        logger.error(
            f"[celery] [{upload_id}] [{worker_id}] retries exhausted, "
            f"failing permanently: {exc}"
        )
        with get_session() as session:
            update_upload_status(
                session, upload_id=upload_id, status=UploadStatus.FAILED
            )
        return False
    raise task.retry(countdown=delays[retry_num], exc=exc)


@app.task(
    name="curator.workers.tasks.process_upload",
    bind=True,
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def process_upload(
    self, upload_id: int, edit_group_id: str, userid: str | None = None
) -> bool:
    """
    Process a single upload request
    """
    worker_id = f"{os.getpid()}-{self.request.id}"
    logger.info(f"[celery] [{upload_id}] [{worker_id}] task started")

    loop = _get_event_loop()
    try:
        result = loop.run_until_complete(process_one(upload_id, edit_group_id))
        return result
    except SourceCdnError as e:
        retry_num = self.request.retries
        logger.warning(
            f"[celery] [{upload_id}] [{worker_id}] source CDN error, requeueing "
            f"(retry {retry_num + 1}/{len(SOURCE_CDN_DELAYS)}): {e}"
        )
        return _requeue_or_fail(self, upload_id, worker_id, SOURCE_CDN_DELAYS, e)
    except StorageError as e:
        retry_num = self.request.retries
        logger.warning(
            f"[celery] [{upload_id}] [{worker_id}] storage error, requeueing "
            f"(retry {retry_num + 1}/{len(STORAGE_ERROR_DELAYS)}): {e}"
        )
        return _requeue_or_fail(self, upload_id, worker_id, STORAGE_ERROR_DELAYS, e)
    except HashLockError as e:
        logger.info(
            f"[celery] [{upload_id}] [{worker_id}] hash locked, requeueing: {e}"
        )
        return _requeue_or_fail(self, upload_id, worker_id, HASH_LOCK_DELAYS, e)
    except Exception as e:
        logger.error(
            f"[celery] [{upload_id}] [{worker_id}] error processing upload: {e}",
            exc_info=True,
        )
        raise
    finally:
        logger.info(f"[celery] [{upload_id}] [{worker_id}] task completed")

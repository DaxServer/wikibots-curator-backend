"""Task enqueuing utilities with rate limiting.

Provides a unified interface for enqueueing upload tasks with proper
rate limiting. All uploads go to QUEUE_NORMAL.
"""

import asyncio
import logging

from sqlalchemy import update
from sqlmodel import col

from curator.app.auth import AccessToken
from curator.app.db import get_session
from curator.app.mediawiki_client import MediaWikiClient
from curator.app.models import UploadRequest
from curator.app.rate_limiter import (
    get_next_upload_delay,
    get_rate_limit_for_batch,
)
from curator.workers.celery import QUEUE_NORMAL
from curator.workers.tasks import process_upload

logger = logging.getLogger(__name__)


async def enqueue_uploads(
    upload_ids: list[int],
    edit_group_id: str,
    userid: str,
    access_token: AccessToken,
) -> list[str]:
    """Enqueue multiple uploads with rate limiting."""
    client = MediaWikiClient(access_token)
    rate_limit = await asyncio.to_thread(
        get_rate_limit_for_batch,
        userid=userid,
        client=client,
    )

    enqueued_task_ids: list[str] = []
    upload_id_to_task_id: dict[int, str] = {}

    for upload_id in upload_ids:
        delay = await asyncio.to_thread(get_next_upload_delay, userid, rate_limit)

        task_result = process_upload.apply_async(
            args=[upload_id, edit_group_id],
            countdown=delay,
            queue=QUEUE_NORMAL,
        )

        task_id = task_result.id
        if isinstance(task_id, str):
            upload_id_to_task_id[upload_id] = task_id
            enqueued_task_ids.append(task_id)

    # Batch update all celery_task_ids in a single transaction
    if upload_id_to_task_id:
        with get_session() as session:
            for upload_id, task_id in upload_id_to_task_id.items():
                session.exec(
                    update(UploadRequest)
                    .where(col(UploadRequest.id) == upload_id)
                    .values(celery_task_id=task_id)
                )
            session.flush()

    logger.info(
        f"[task_enqueuer] Enqueued {len(enqueued_task_ids)} uploads to queue {QUEUE_NORMAL}"
    )

    return enqueued_task_ids

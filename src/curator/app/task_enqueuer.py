"""Task enqueuing utilities with rate limiting.

Provides a unified interface for enqueueing upload tasks with proper
rate limiting and queue selection based on user privilege status.
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
    RateLimitInfo,
    get_next_upload_delay,
    get_rate_limit_for_batch,
)
from curator.workers.celery import QUEUE_NORMAL, QUEUE_PRIVILEGED
from curator.workers.tasks import process_upload

logger = logging.getLogger(__name__)


async def get_queue_for_user(
    userid: str, client: MediaWikiClient
) -> tuple[str, RateLimitInfo]:
    """Get the appropriate queue and rate limit info for a user.

    Returns a tuple of (queue_name, rate_limit_info).
    """
    rate_limit = await asyncio.to_thread(
        get_rate_limit_for_batch,
        userid=userid,
        client=client,
    )
    queue = QUEUE_PRIVILEGED if rate_limit.is_privileged else QUEUE_NORMAL
    return queue, rate_limit


async def enqueue_uploads(
    upload_ids: list[int],
    edit_group_id: str,
    userid: str,
    access_token: AccessToken,
) -> list[str]:
    """Enqueue multiple uploads with rate limiting.

    This is the main entry point for enqueueing uploads. It:
    1. Creates a MediaWikiClient with the access token
    2. Determines the appropriate queue based on user privilege
    3. Enqueues each upload with proper rate limiting delays
    4. Updates all celery_task_ids in a single batch operation

    Args:
        upload_ids: List of upload request IDs to enqueue
        edit_group_id: The batch edit group ID
        userid: The user ID
        access_token: The decrypted access token

    Returns:
        List of enqueued task IDs
    """
    client = MediaWikiClient(access_token)
    queue, rate_limit = await get_queue_for_user(userid, client)

    enqueued_task_ids: list[str] = []
    upload_id_to_task_id: dict[int, str] = {}

    for upload_id in upload_ids:
        delay = await asyncio.to_thread(get_next_upload_delay, userid, rate_limit)

        task_result = process_upload.apply_async(
            args=[upload_id, edit_group_id],
            countdown=delay,
            queue=queue,
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
        f"[task_enqueuer] Enqueued {len(enqueued_task_ids)} uploads to queue {queue} "
        f"(privileged={rate_limit.is_privileged})"
    )

    return enqueued_task_ids

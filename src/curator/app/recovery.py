"""Startup recovery for uploads stuck in queued state after a Redis restart."""

import asyncio
import logging
from collections import defaultdict

from mwoauth import AccessToken

from curator.app.config import redis_client
from curator.app.crypto import decrypt_access_token
from curator.app.dal import get_queued_uploads_for_recovery, mark_uploads_expired
from curator.app.db import get_session
from curator.app.mediawiki_client import MediaWikiClient
from curator.app.task_enqueuer import enqueue_uploads

logger = logging.getLogger(__name__)

SENTINEL_KEY = "curator:started"


def _validate_token(access_token_cipher: str) -> AccessToken:
    """Decrypt and validate a token against MediaWiki, closing the HTTP client after."""
    access_token = decrypt_access_token(access_token_cipher)
    client = MediaWikiClient(access_token)
    try:
        client.get_user_groups()
    finally:
        client._client.close()
    return access_token


async def recover_queued_uploads() -> None:
    """Re-enqueue uploads stuck in queued state after a Redis restart."""
    if redis_client.exists(SENTINEL_KEY):
        return

    with get_session() as session:
        queued = get_queued_uploads_for_recovery(session)

    groups: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
    for upload_id, userid, access_token_cipher, edit_group_id in queued:
        groups[(userid, edit_group_id)].append((upload_id, access_token_cipher))

    expired_ids: list[int] = []

    for (userid, edit_group_id), uploads in groups.items():
        upload_ids = [uid for uid, _ in uploads]

        try:
            access_token = await asyncio.to_thread(_validate_token, uploads[0][1])
        except Exception:
            logger.warning(
                f"[recovery] Token invalid for user {userid}, marking {len(upload_ids)} uploads as failed"
            )
            expired_ids.extend(upload_ids)
            continue

        await enqueue_uploads(
            upload_ids=upload_ids,
            edit_group_id=edit_group_id,
            userid=userid,
            access_token=access_token,
        )
        logger.info(
            f"[recovery] Re-enqueued {len(upload_ids)} uploads for user {userid}"
        )

    if expired_ids:
        with get_session() as session:
            mark_uploads_expired(session, expired_ids)

    redis_client.set(SENTINEL_KEY, "1")
    logger.info("[recovery] Recovery complete, sentinel key set")

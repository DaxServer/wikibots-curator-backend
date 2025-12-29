import logging
from typing import Literal

from curator.app.commons import (
    DuplicateUploadError,
    check_title_blacklisted,
    upload_file_chunked,
)
from curator.app.crypto import decrypt_access_token
from curator.app.dal import (
    clear_upload_access_token,
    get_upload_request_by_id,
    update_upload_status,
)
from curator.app.db import get_session
from curator.app.ingest.handlers.mapillary_handler import MapillaryHandler
from curator.app.models import (
    StructuredError,
    UploadRequest,
)
from curator.asyncapi import DuplicateError, GenericError, TitleBlacklistedError

logger = logging.getLogger(__name__)


def _cleanup(session, item: UploadRequest | None = None):
    try:
        if item:
            clear_upload_access_token(session, upload_id=item.id)
    finally:
        session.close()


def _success(session, item: UploadRequest, url) -> bool:
    update_upload_status(session, upload_id=item.id, status="completed", success=url)
    _cleanup(session, item)
    return True


def _fail(
    session,
    upload_id: int,
    status: Literal["failed", "duplicate"],
    item: UploadRequest | None,
    structured_error: StructuredError,
) -> bool:
    update_upload_status(
        session,
        upload_id=upload_id,
        status=status,
        error=structured_error,
    )
    _cleanup(session, item)
    return False


async def process_one(upload_id: int) -> bool:
    logger.info(f"[{upload_id}] processing upload")
    session = next(get_session())
    item = None
    try:
        item = get_upload_request_by_id(session, upload_id)
        if not item:
            logger.error(f"[{upload_id}] upload not found")
            _cleanup(session, item)
            return False

        if item.status != "queued":
            logger.error(f"[{upload_id}/{item.batchid}] upload not in queued status")
            _cleanup(session, item)
            return False

        update_upload_status(session, upload_id=item.id, status="in_progress")

        if not item.access_token:
            logger.error(f"[{upload_id}/{item.batchid}] missing access token")
            return _fail(
                session=session,
                upload_id=item.id,
                status="failed",
                item=item,
                structured_error=GenericError(
                    message="Missing access token",
                ),
            )

        access_token = decrypt_access_token(item.access_token)
        if not item.user:
            logger.error(f"[{upload_id}/{item.batchid}] user not found for upload")
            return _fail(
                session=session,
                upload_id=item.id,
                status="failed",
                item=item,
                structured_error=GenericError(
                    message="User not found for upload",
                ),
            )
        username = item.user.username

        # Check if the title is blacklisted
        logger.info(f"[{upload_id}/{item.batchid}] checking if title is blacklisted")
        is_blacklisted, reason = check_title_blacklisted(
            access_token, username, item.filename, upload_id, item.batchid
        )
        if is_blacklisted:
            logger.warning(
                f"[{upload_id}/{item.batchid}] title {item.filename} is blacklisted: {reason}"
            )
            return _fail(
                session=session,
                upload_id=item.id,
                status="failed",
                item=item,
                structured_error=TitleBlacklistedError(
                    message=reason,
                ),
            )

        logger.info(
            f"[{upload_id}/{item.batchid}] fetching Mapillary image metadata for photo {item.key} from collection {item.collection}"
        )
        handler = MapillaryHandler()
        image = await handler.fetch_image_metadata(item.key, item.collection)
        image_url = image.url_original

        logger.info(f"[{upload_id}/{item.batchid}] uploading file")
        edit_summary = f"Uploaded via Curator from Mapillary image {image.id} (batch {item.batchid})"
        upload_result = upload_file_chunked(
            upload_id=item.id,
            batch_id=item.batchid,
            file_name=item.filename,
            file_url=image_url,
            wikitext=item.wikitext,
            edit_summary=edit_summary,
            access_token=access_token,
            username=username,
            sdc=item.sdc,
            labels=item.labels,
        )

        logger.info(
            f"[{upload_id}/{item.batchid}] successfully uploaded to {upload_result.get('url')}"
        )
        return _success(session, item, upload_result.get("url"))
    except DuplicateUploadError as e:
        batchid = f"/{item.batchid}" if item else ""
        logger.error(f"[{upload_id}{batchid}] duplicate upload detected")
        return _fail(
            session,
            upload_id,
            "duplicate",
            item,
            DuplicateError(
                message=str(e),
                links=e.duplicates,
            ),
        )
    except Exception as e:
        batchid = f"/{item.batchid}" if item else ""
        logger.error(
            f"[{upload_id}{batchid}] error processing upload: {e}", exc_info=True
        )
        return _fail(
            session,
            upload_id,
            "failed",
            item,
            GenericError(message=str(e)),
        )

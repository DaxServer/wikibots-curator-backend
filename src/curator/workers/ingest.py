import asyncio
import logging
from typing import Literal

from sqlmodel import Session

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
from curator.app.db import engine
from curator.app.handlers.mapillary_handler import MapillaryHandler
from curator.app.models import (
    StructuredError,
    UploadRequest,
)
from curator.app.sdc_v2 import build_statements_from_mapillary_image
from curator.asyncapi import (
    DuplicateError,
    GenericError,
    Statement,
    TitleBlacklistedError,
)

logger = logging.getLogger(__name__)

# Maximum number of retries for uploadstash-file-not-found errors
MAX_UPLOADSTASH_TRIES = 2


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


def _is_uploadstash_file_not_found_error(error_message: str) -> bool:
    """Check if the error message indicates an uploadstash-file-not-found error."""
    return (
        "uploadstash-file-not-found" in error_message
        and "not found in stash" in error_message
    )


async def _upload_with_retry(
    item: UploadRequest,
    access_token: str,
    username: str,
    image_url: str,
    sdc: list[Statement] | None,
):
    """
    Upload a file with retry logic for uploadstash-file-not-found errors
    """
    for attempt in range(MAX_UPLOADSTASH_TRIES):
        try:
            logger.info(
                f"[{item.id}/{item.batchid}] uploading file (attempt {attempt + 1}/{MAX_UPLOADSTASH_TRIES})"
            )

            return upload_file_chunked(
                upload_id=item.id,
                batch_id=item.batchid,
                file_name=item.filename,
                file_url=image_url,
                wikitext=item.wikitext,
                edit_summary=f"Uploaded via Curator from Mapillary image {item.key} (batch {item.batchid})",
                access_token=access_token,
                username=username,
                sdc=sdc,
                labels=item.labels,
            )
        except DuplicateUploadError:
            # Let DuplicateUploadError pass through to be handled by the outer exception handler
            raise
        except Exception as upload_error:
            error_message = str(upload_error)

            # Check if this is an uploadstash-file-not-found error and we haven't exceeded max retries
            if (
                _is_uploadstash_file_not_found_error(error_message)
                and attempt < MAX_UPLOADSTASH_TRIES - 1
            ):
                logger.warning(
                    f"[{item.id}/{item.batchid}] uploadstash-file-not-found error on attempt {attempt + 1}, "
                    f"retrying in 2 seconds... (retry {attempt + 1}/{MAX_UPLOADSTASH_TRIES})"
                )
                # Wait 2 seconds before retrying
                await asyncio.sleep(2)
                continue

            # Either not an uploadstash error or we've exceeded max retries
            if _is_uploadstash_file_not_found_error(error_message):
                logger.error(
                    f"[{item.id}/{item.batchid}] uploadstash-file-not-found error persisted after {MAX_UPLOADSTASH_TRIES} attempts"
                )

            raise


async def process_one(upload_id: int) -> bool:
    logger.info(f"[{upload_id}] processing upload")
    session = Session(engine)
    item = None
    try:
        item = get_upload_request_by_id(session, upload_id)
        if not item:
            logger.error(f"[{upload_id}] upload not found")
            return _fail(
                session,
                upload_id,
                "failed",
                None,
                GenericError(message="Upload request not found"),
            )

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

        # Use last_editor's username if last_edited_by is set (admin retry), otherwise use original user's username
        username = item.last_editor.username if item.last_editor else item.user.username

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

        sdc = build_statements_from_mapillary_image(
            image=image,
            include_default_copyright=not item.copyright_override,
        )

        # Upload with retry logic for uploadstash-file-not-found errors
        upload_result = await _upload_with_retry(
            item=item,
            access_token=access_token,
            username=username,
            image_url=image_url,
            sdc=sdc,
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

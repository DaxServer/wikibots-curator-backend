import asyncio
import logging
from typing import Literal

from sqlmodel import Session

from curator.app.commons import (
    DuplicateUploadError,
    check_title_blacklisted,
    fetch_sdc_from_api,
    get_commons_site,
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
from curator.app.sdc_merge import merge_sdc_statements
from curator.app.sdc_v2 import build_statements_from_mapillary_image
from curator.asyncapi import (
    DuplicatedSdcNotUpdatedError,
    DuplicatedSdcUpdatedError,
    DuplicateError,
    GenericError,
    Label,
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
    status: Literal[
        "failed", "duplicate", "duplicated_sdc_updated", "duplicated_sdc_not_updated"
    ],
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
    """Check if the error message indicates an uploadstash-file-not-found error"""
    return (
        "uploadstash-file-not-found" in error_message
        and "not found in stash" in error_message
    )


async def _handle_duplicate_with_sdc_merge(
    item: UploadRequest,
    access_token: str,
    username: str,
    sdc: list[Statement] | None,
    duplicate_error: DuplicateUploadError,
) -> tuple[str | None, str | None]:
    """
    Handle duplicate upload by attempting to merge SDC
    """
    batchid = f"/{item.batchid}"
    upload_id = item.id

    if not duplicate_error.duplicates or len(duplicate_error.duplicates) == 0:
        logger.warning(f"[{upload_id}{batchid}] no duplicate files found")
        return None, None

    if sdc is None:
        logger.info(
            f"[{upload_id}{batchid}] no SDC to merge, falling back to duplicate status"
        )
        return None, None

    duplicate_file = duplicate_error.duplicates[0]
    duplicate_title = duplicate_file.title

    logger.info(
        f"[{upload_id}{batchid}] merging SDC with existing file {duplicate_title}"
    )

    site = get_commons_site(access_token, username)

    file_page = FilePage(Page(site, title=duplicate_title, ns=6))
    existing_sdc, existing_labels = fetch_sdc_from_api(site, f"M{file_page.pageid}")

    # Convert item.labels to Label model if it's a dict (from JSON storage)
    item_label = None
    if item.labels:
        item_label = (
            Label.model_validate(item.labels)
            if isinstance(item.labels, dict)
            else item.labels
        )

    # Get existing label matching the item's label language
    existing_label = None
    if item_label and existing_labels:
        existing_label = existing_labels.get(item_label.language)

    if existing_sdc is None:
        logger.info(f"[{upload_id}{batchid}] no existing SDC, applying new SDC")
        merged_sdc = sdc
    else:
        merged_sdc = merge_sdc_statements(existing_sdc, sdc)
        logger.info(
            f"[{upload_id}{batchid}] merged {len(sdc)} new statements with {len(existing_sdc)} existing statements, result: {len(merged_sdc)} statements"
        )

    # Check if merged SDC and labels are equal to existing SDC and labels
    sdc_equal = existing_sdc is not None and _are_sdc_equal(existing_sdc, merged_sdc)
    labels_equal = _are_labels_equal(existing_label, item_label)

    logger.info(
        f"[{upload_id}{batchid}] SDC equality check: existing={len(existing_sdc) if existing_sdc else 0}, "
        f"merged={len(merged_sdc)}, equal={sdc_equal}, labels_equal={labels_equal}"
    )

    if sdc_equal and labels_equal:
        logger.info(
            f"[{upload_id}{batchid}] merged SDC and labels are equal to existing, skipping API request"
        )
        return duplicate_file.url, "duplicated_sdc_not_updated"

    if apply_sdc(
        site=site,
        file_page=file_page,
        sdc=merged_sdc,
        edit_summary=f"Merging SDC from Mapillary image {item.key} (batch {item.batchid})",
        labels=item_label,
    ):
        logger.info(f"[{upload_id}{batchid}] successfully applied SDC to existing file")

    return duplicate_file.url, "duplicated_sdc_updated"


def _are_labels_equal(labels1: Label | None, labels2: Label | None) -> bool:
    """Check if two labels are equal"""
    return labels1 == labels2


def _are_sdc_equal(sdc1: list[Statement], sdc2: list[Statement]) -> bool:
    """
    Check if two SDC statement lists are equal (excluding 'id' and 'hash' fields which are Commons-specific)
    """
    if len(sdc1) != len(sdc2):
        return False

    def remove_hashes(d: dict) -> dict:
        """Recursively remove hash and datatype fields from a dict"""
        if not isinstance(d, dict):
            return d

        result = {}
        for key, value in d.items():
            if key in ("hash", "datatype"):
                continue
            if isinstance(value, dict):
                result[key] = remove_hashes(value)
            elif isinstance(value, list):
                result[key] = [
                    remove_hashes(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    # Convert both to comparable format, excluding 'id' and all 'hash' fields
    def dump_without_id_hash(stmt: Statement) -> dict:
        dumped = stmt.model_dump(mode="json", by_alias=True, exclude_none=True)
        dumped.pop("id", None)
        return remove_hashes(dumped)

    sdc1_dumped = sorted(
        [dump_without_id_hash(s) for s in sdc1],
        key=lambda x: str(x),
    )
    sdc2_dumped = sorted(
        [dump_without_id_hash(s) for s in sdc2],
        key=lambda x: str(x),
    )

    equal = sdc1_dumped == sdc2_dumped
    if not equal:
        # Log first difference for debugging
        for i, (d1, d2) in enumerate(zip(sdc1_dumped, sdc2_dumped)):
            if d1 != d2:
                logger.debug(f"First difference at index {i}:")
                logger.debug(f"  existing: {d1}")
                logger.debug(f"  merged:   {d2}")
                break

    return equal


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
        logger.info(
            f"[{upload_id}{batchid}] duplicate upload detected, attempting SDC merge"
        )

        if item is None:
            # Can't merge without item info
            return _fail(
                session,
                upload_id,
                "duplicate",
                None,
                DuplicateError(
                    message=str(e),
                    links=e.duplicates,
                ),
            )

        merge_result, merge_status = await _handle_duplicate_with_sdc_merge(
            item=item,
            access_token=access_token,
            username=username,
            sdc=sdc,
            duplicate_error=e,
        )

        if merge_result:
            if merge_status == "duplicated_sdc_updated":
                return _fail(
                    session,
                    upload_id,
                    "duplicated_sdc_updated",
                    item,
                    DuplicatedSdcUpdatedError(
                        message=str(e),
                        links=e.duplicates,
                    ),
                )
            elif merge_status == "duplicated_sdc_not_updated":
                return _fail(
                    session,
                    upload_id,
                    "duplicated_sdc_not_updated",
                    item,
                    DuplicatedSdcNotUpdatedError(
                        message=str(e),
                        links=e.duplicates,
                    ),
                )
            else:
                # Should not happen, but handle gracefully
                return _success(session, item, merge_result)
        else:
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

import asyncio
import logging
from typing import Literal

from curator.app.commons import (
    DuplicateUploadError,
    apply_sdc,
    create_isolated_site,
    fetch_sdc_from_api,
    upload_file_chunked,
)
from curator.app.crypto import decrypt_access_token
from curator.app.dal import (
    clear_upload_access_token,
    get_upload_request_by_id,
    update_upload_status,
)
from curator.app.db import get_session
from curator.app.mediawiki_client import MediaWikiClient, create_mediawiki_client
from curator.app.models import (
    StructuredError,
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
from curator.handlers.mapillary_handler import MapillaryHandler

logger = logging.getLogger(__name__)

# Maximum number of retries for uploadstash-file-not-found errors
MAX_UPLOADSTASH_TRIES = 2


def _cleanup(session, upload_id: int):
    clear_upload_access_token(session, upload_id=upload_id)


def _success(session, upload_id: int, url) -> bool:
    update_upload_status(session, upload_id=upload_id, status="completed", success=url)
    _cleanup(session, upload_id)
    return True


def _fail(
    session,
    upload_id: int,
    status: Literal[
        "failed", "duplicate", "duplicated_sdc_updated", "duplicated_sdc_not_updated"
    ],
    structured_error: StructuredError,
) -> bool:
    update_upload_status(
        session,
        upload_id=upload_id,
        status=status,
        error=structured_error,
    )
    _cleanup(session, upload_id)
    return False


def _is_uploadstash_file_not_found_error(error_message: str) -> bool:
    """Check if the error message indicates an uploadstash-file-not-found error"""
    return (
        "uploadstash-file-not-found" in error_message
        and "not found in stash" in error_message
    )


async def _handle_duplicate_with_sdc_merge(
    upload_id: int,
    batch_id: int,
    key: str,
    labels: dict | Label | None,
    site,
    sdc: list[Statement] | None,
    duplicate_error: DuplicateUploadError,
    edit_group_id: str,
    mediawiki_client: MediaWikiClient,
) -> tuple[str | None, str | None]:
    """
    Handle duplicate upload by attempting to merge SDC
    """
    if not duplicate_error.duplicates or len(duplicate_error.duplicates) == 0:
        logger.warning(f"[{upload_id}/{batch_id}] no duplicate files found")
        return None, None

    if sdc is None:
        logger.info(
            f"[{upload_id}/{batch_id}] no SDC to merge, falling back to duplicate status"
        )
        return None, None

    duplicate_file = duplicate_error.duplicates[0]
    duplicate_title = duplicate_file.title

    logger.info(
        f"[{upload_id}/{batch_id}] merging SDC with existing file {duplicate_title}"
    )

    # Fetch existing SDC and labels
    existing_sdc, existing_labels = fetch_sdc_from_api(
        duplicate_title, mediawiki_client
    )

    # Convert labels to Label model if it's a dict (from JSON storage)
    item_label = None
    if labels:
        item_label = (
            Label.model_validate(labels) if isinstance(labels, dict) else labels
        )

    # Get existing label matching the item's label language
    existing_label = None
    if item_label and existing_labels:
        existing_label = existing_labels.get(item_label.language)

    if existing_sdc is None:
        logger.info(f"[{upload_id}/{batch_id}] no existing SDC, applying new SDC")
        merged_sdc = sdc
    else:
        merged_sdc = merge_sdc_statements(existing_sdc, sdc)
        logger.info(
            f"[{upload_id}/{batch_id}] merged {len(sdc)} new statements with {len(existing_sdc)} "
            f"existing statements, result: {len(merged_sdc)} statements"
        )

    # Check if merged SDC and labels are equal to existing SDC and labels
    sdc_equal = existing_sdc is not None and _are_sdc_equal(existing_sdc, merged_sdc)
    labels_equal = _are_labels_equal(existing_label, item_label)

    logger.info(
        f"[{upload_id}/{batch_id}] SDC equality check: existing={len(existing_sdc) if existing_sdc else 0}, "
        f"merged={len(merged_sdc)}, equal={sdc_equal}, labels_equal={labels_equal}"
    )

    if sdc_equal and labels_equal:
        logger.info(
            f"[{upload_id}/{batch_id}] merged SDC and labels are equal to existing, skipping API request"
        )
        return duplicate_file.url, "duplicated_sdc_not_updated"

    edit_summary = (
        f"Merging SDC from Mapillary image {key} (batch {batch_id}) "
        f"([[:toolforge:editgroups-commons/b/curator/{edit_group_id}|details]])"
    )

    if apply_sdc(
        file_title=duplicate_title,
        sdc=merged_sdc,
        edit_summary=edit_summary,
        labels=item_label,
        mediawiki_client=mediawiki_client,
    ):
        logger.info(
            f"[{upload_id}/{batch_id}] successfully applied SDC to existing file"
        )

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
    upload_id: int,
    batch_id: int,
    filename: str,
    key: str,
    wikitext: str,
    labels: Label | None,
    site,
    image_url: str,
    sdc: list[Statement] | None,
    edit_group_id: str,
    mediawiki_client: MediaWikiClient,
):
    """
    Upload a file with retry logic for uploadstash-file-not-found errors
    """
    for attempt in range(MAX_UPLOADSTASH_TRIES):
        try:
            logger.info(
                f"[{upload_id}/{batch_id}] uploading file (attempt {attempt + 1}/{MAX_UPLOADSTASH_TRIES})"
            )

            edit_summary = (
                f"Uploaded via Curator from Mapillary image {key} (batch {batch_id}) "
                f"([[:toolforge:editgroups-commons/b/curator/{edit_group_id}|details]])"
            )

            return await site.run(
                upload_file_chunked,
                filename,
                image_url,
                wikitext,
                edit_summary,
                upload_id,
                batch_id,
                mediawiki_client,
                sdc,
                labels,
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
                    f"[{upload_id}/{batch_id}] uploadstash-file-not-found error on attempt {attempt + 1}, "
                    f"retrying in 2 seconds... (retry {attempt + 1}/{MAX_UPLOADSTASH_TRIES})"
                )
                # Wait 2 seconds before retrying
                await asyncio.sleep(2)
                continue

            # Either not an uploadstash error or we've exceeded max retries
            if _is_uploadstash_file_not_found_error(error_message):
                logger.error(
                    f"[{upload_id}/{batch_id}] uploadstash-file-not-found error persisted after {MAX_UPLOADSTASH_TRIES} attempts"
                )

            raise


async def process_one(upload_id: int, edit_group_id: str) -> bool:
    logger.info(f"[{upload_id}] processing upload")

    # 1. Fetch data and set in_progress (Short session)
    try:
        with get_session() as session:
            item = get_upload_request_by_id(session, upload_id)
            if not item:
                logger.error(f"[{upload_id}] upload not found")
                # We can't even fail it in DB if it's not found
                return False

            if item.status != "queued":
                logger.error(
                    f"[{upload_id}/{item.batchid}] upload not in queued status"
                )
                return False

            update_upload_status(session, upload_id=upload_id, status="in_progress")

            if not item.access_token:
                logger.error(f"[{upload_id}/{item.batchid}] missing access token")
                return _fail(
                    session=session,
                    upload_id=upload_id,
                    status="failed",
                    structured_error=GenericError(message="Missing access token"),
                )

            if not item.user:
                logger.error(f"[{upload_id}/{item.batchid}] user not found for upload")
                return _fail(
                    session=session,
                    upload_id=upload_id,
                    status="failed",
                    structured_error=GenericError(message="User not found for upload"),
                )

            # Extract all needed values to avoid DetachedInstanceError outside this block
            access_token = decrypt_access_token(item.access_token)
            username = (
                item.last_editor.username if item.last_editor else item.user.username
            )
            filename = item.filename
            key = item.key
            batchid = item.batchid
            collection = item.collection
            wikitext = item.wikitext
            labels = item.labels
            copyright_override = item.copyright_override
    except Exception as e:
        logger.error(f"[{upload_id}] Error in initial fetch: {e}")
        with get_session() as session:
            return _fail(
                session=session,
                upload_id=upload_id,
                status="failed",
                structured_error=GenericError(message=f"Initial fetch error: {e}"),
            )

    # 2. Long running operations (NO DB SESSION)
    try:
        # Create isolated site wrapper for this job
        site = create_isolated_site(access_token, username)

        # Create MediaWiki API client for this job
        mediawiki_client = create_mediawiki_client(access_token)

        # Check if title is blacklisted
        logger.info(f"[{upload_id}/{batchid}] checking if title is blacklisted")

        is_blacklisted, reason = await asyncio.to_thread(
            mediawiki_client.check_title_blacklisted, filename
        )

        if is_blacklisted:
            logger.warning(
                f"[{upload_id}/{batchid}] title {filename} is blacklisted: {reason}"
            )
            with get_session() as session:
                return _fail(
                    session=session,
                    upload_id=upload_id,
                    status="failed",
                    structured_error=TitleBlacklistedError(message=reason),
                )

        logger.info(
            f"[{upload_id}/{batchid}] fetching Mapillary image metadata for photo {key} from collection {collection}"
        )
        handler = MapillaryHandler()
        image = await handler.fetch_image_metadata(key, collection)
        image_url = image.urls.original

        sdc = build_statements_from_mapillary_image(
            image=image,
            include_default_copyright=not copyright_override,
        )

        # Upload with retry logic for uploadstash-file-not-found errors
        upload_result = await _upload_with_retry(
            upload_id=upload_id,
            batch_id=batchid,
            filename=filename,
            key=key,
            wikitext=wikitext,
            labels=labels,
            site=site,
            image_url=image_url,
            sdc=sdc,
            edit_group_id=edit_group_id,
            mediawiki_client=mediawiki_client,
        )

        logger.info(
            f"[{upload_id}/{batchid}] successfully uploaded to {upload_result.get('url')}"
        )

        with get_session() as session:
            return _success(session, upload_id, upload_result.get("url"))

    except DuplicateUploadError as e:
        logger.info(
            f"[{upload_id}/{batchid}] duplicate upload detected, attempting SDC merge"
        )

        # For SDC merge, we passing extracted data directly
        merge_result, merge_status = await _handle_duplicate_with_sdc_merge(
            upload_id=upload_id,
            batch_id=batchid,
            key=key,
            labels=labels,
            site=site,
            sdc=sdc,
            duplicate_error=e,
            edit_group_id=edit_group_id,
            mediawiki_client=mediawiki_client,
        )

        with get_session() as session:
            if merge_result:
                if merge_status == "duplicated_sdc_updated":
                    return _fail(
                        session,
                        upload_id,
                        "duplicated_sdc_updated",
                        DuplicatedSdcUpdatedError(message=str(e), links=e.duplicates),
                    )
                elif merge_status == "duplicated_sdc_not_updated":
                    return _fail(
                        session,
                        upload_id,
                        "duplicated_sdc_not_updated",
                        DuplicatedSdcNotUpdatedError(
                            message=str(e), links=e.duplicates
                        ),
                    )
                else:
                    return _success(session, upload_id, merge_result)
            else:
                return _fail(
                    session,
                    upload_id,
                    "duplicate",
                    DuplicateError(message=str(e), links=e.duplicates),
                )

    except Exception as e:
        logger.error(
            f"[{upload_id}/{batchid}] error processing upload: {e}", exc_info=True
        )
        with get_session() as session:
            return _fail(
                session,
                upload_id,
                "failed",
                GenericError(message=str(e)),
            )

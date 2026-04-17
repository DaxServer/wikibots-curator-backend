import hashlib
import logging
import time
from tempfile import NamedTemporaryFile
from typing import IO, Any, Optional

import requests

from curator.asyncapi import Label, Statement
from curator.core.config import HTTP_RETRY_DELAYS, redis_client
from curator.core.errors import DuplicateUploadError, HashLockError, SourceCdnError
from curator.mediawiki.client import MediaWikiClient

logger = logging.getLogger(__name__)

# Lock TTL in seconds (1 minute)
HASH_LOCK_TTL = 60

# Cache key template for hash locks
_HASH_LOCK_KEY = "hashlock:{hash}"


def upload_file_chunked(
    file_name: str,
    file_url: str,
    wikitext: str,
    edit_summary: str,
    upload_id: int,
    batch_id: int,
    mediawiki_client: MediaWikiClient,
    sdc: Optional[list[Statement]] = None,
    labels: Optional[Label] = None,
) -> dict:
    """
    Upload a file to Commons using MediaWikiClient's upload_file method.

    - Uses chunked uploads
    - Streams download to temp file for memory efficiency
    - Returns a dict payload {"result": "success", "title": ..., "url": ...}.
    """
    with NamedTemporaryFile() as temp_file:
        # Download directly to temp file, get hash
        file_hash = download_file(file_url, temp_file, upload_id, batch_id)
        logger.info(
            f"[{upload_id}/{batch_id}] Image downloaded. File hash: {file_hash}"
        )

        # Check for duplicates before upload using hash
        duplicates_list = mediawiki_client.find_duplicates(file_hash)
        if len(duplicates_list) > 0:
            raise DuplicateUploadError(
                duplicates_list,
                f"File {file_name} already exists on Commons",
            )

        # Acquire hash lock to prevent race condition on duplicate files
        lock_key = _HASH_LOCK_KEY.format(hash=file_hash)
        if not redis_client.set(lock_key, "1", nx=True, ex=HASH_LOCK_TTL):
            raise HashLockError(f"Hash {file_hash} is locked by another worker")

        try:
            # Upload using temp file path
            upload_result = mediawiki_client.upload_file(
                filename=file_name,
                file_path=temp_file.name,
                wikitext=wikitext,
                edit_summary=edit_summary,
                file_sha1=file_hash,
            )

            # Check for upload errors
            if not upload_result.success:
                raise ValueError(upload_result.error or "Upload failed")

            # Apply SDC after successful upload
            apply_sdc(file_name, mediawiki_client, sdc, edit_summary, labels)

            return {
                "result": "success",
                "title": upload_result.title,
                "url": upload_result.url,
            }
        finally:
            redis_client.delete(lock_key)


def download_file(
    file_url: str, temp_file: IO[bytes], upload_id: int = 0, batch_id: int = 0
) -> str:
    """Download file to temp file using streaming, returns SHA1 hash"""
    max_attempts = len(HTTP_RETRY_DELAYS) + 1
    for attempt in range(max_attempts):
        resp = None
        is_last_attempt = attempt == max_attempts - 1
        delay = HTTP_RETRY_DELAYS[attempt] if not is_last_attempt else 0

        # Reset temp file for retry
        temp_file.seek(0)
        temp_file.truncate()

        try:
            resp = requests.get(file_url, stream=True, timeout=60)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "application/x-php" in content_type:
                resp.close()
                if is_last_attempt:
                    raise ValueError(
                        f"Failed to download image from {file_url}: "
                        f"received application/x-php content type after {max_attempts} attempts"
                    )
                logger.warning(
                    f"[{upload_id}/{batch_id}] Received application/x-php instead of image "
                    f"(attempt {attempt + 1}/{max_attempts}), "
                    f"retrying in {delay} seconds"
                )
                time.sleep(delay)
                continue

            # Stream download: write chunks to temp file and update hash
            sha1 = hashlib.sha1()
            for chunk in resp.iter_content(chunk_size=8192):
                temp_file.write(chunk)
                sha1.update(chunk)

            return sha1.hexdigest()
        except requests.exceptions.RequestException as e:
            if resp is not None:
                resp.close()
            if is_last_attempt:
                logger.error(
                    f"[{upload_id}/{batch_id}] Image download failed after "
                    f"{max_attempts}/{max_attempts} attempts: {e}"
                )
                if (
                    isinstance(e, requests.exceptions.HTTPError)
                    and e.response is not None
                    and e.response.status_code >= 500
                ):
                    raise SourceCdnError(str(e)) from e
                raise
            logger.warning(
                f"[{upload_id}/{batch_id}] Image download "
                f"(attempt {attempt + 1}/{max_attempts}) failed, "
                f"retrying in {delay} seconds: {e}"
            )
            time.sleep(delay)
            continue

    raise AssertionError("Unreachable")


def _build_sdc_payload(
    sdc: Optional[list[Statement]], labels: Optional[Label]
) -> dict[str, Any]:
    """
    Build the wbeditentity data payload from SDC statements and labels
    """
    data: dict[str, Any] = {}

    if sdc:
        data["claims"] = []
        for s in sdc:
            if not isinstance(s, Statement):
                s = Statement.model_validate(s)
            data["claims"].append(
                s.model_dump(mode="json", by_alias=True, exclude_none=True)
            )

    if labels:
        if not isinstance(labels, Label):
            labels = Label.model_validate(labels)
        data["labels"] = [
            labels.model_dump(mode="json", by_alias=True, exclude_none=True)
        ]

    return data


def apply_sdc(
    file_title: str,
    mediawiki_client: MediaWikiClient,
    sdc: Optional[list[Statement]] = None,
    edit_summary: str = "",
    labels: Optional[Label] = None,
) -> bool:
    """
    Apply SDC to an existing file on Commons using MediaWikiClient
    """
    data = _build_sdc_payload(sdc, labels)

    if not data:
        return False

    # Strip "File:" prefix if present
    filename = file_title
    if filename.startswith("File:"):
        filename = filename[5:]

    return mediawiki_client.apply_sdc(
        filename=filename,
        sdc=data.get("claims"),
        labels=data.get("labels"),
        edit_summary=edit_summary,
    )


def fetch_sdc_from_api(
    title: str, mediawiki_client: MediaWikiClient
) -> tuple[list[Statement] | None, dict[str, Label] | None]:
    """
    Fetch SDC data and labels.
    """
    # Use MediaWikiClient to fetch raw data
    sdc, labels = mediawiki_client.fetch_sdc(title)

    if sdc is None:
        return None, None

    # Convert raw dicts to Statement and Label models
    existing_sdc = []
    for prop, claim_list in sdc.items():
        for claim_dict in claim_list:
            stmt = Statement.model_validate(claim_dict)
            existing_sdc.append(stmt)

    # Convert labels to Label model objects
    existing_labels = None
    if labels:
        existing_labels = {
            lang: Label.model_validate(lbl) for lang, lbl in labels.items()
        }

    return existing_sdc, existing_labels

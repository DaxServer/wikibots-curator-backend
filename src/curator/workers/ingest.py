import json
from typing import Literal

from curator.app.commons import DuplicateUploadError, upload_file_chunked
from curator.app.crypto import decrypt_access_token
from curator.app.dal import (
    clear_upload_access_token,
    get_upload_request_by_id,
    update_upload_status,
)
from curator.app.db import get_session
from curator.app.ingest.handlers.mapillary_handler import MapillaryHandler
from curator.app.models import (
    DuplicateError,
    GenericError,
    StructuredError,
    UploadRequest,
)


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
    session = next(get_session())
    item = None
    try:
        item = get_upload_request_by_id(session, upload_id)
        if not item:
            _cleanup(session)
            return False

        update_upload_status(session, upload_id=item.id, status="in_progress")

        handler = MapillaryHandler()
        image = await handler.fetch_image_metadata(item.key, item.collection or "")
        sdc_json = json.loads(item.sdc) if item.sdc else None
        image_url = image.url_original
        if not item.access_token:
            raise Exception("Missing access token")
        access_token = decrypt_access_token(item.access_token)
        username = item.user.username

        edit_summary = f"Uploaded via Curator from Mapillary image {image.id}"
        upload_result = upload_file_chunked(
            file_name=item.filename,
            file_url=image_url,
            wikitext=item.wikitext,
            edit_summary=edit_summary,
            access_token=access_token,
            username=username,
            sdc=sdc_json,
            labels=item.labels,
        )

        return _success(session, item, upload_result.get("url"))
    except DuplicateUploadError as e:
        structured_error: DuplicateError = {
            "type": "duplicate",
            "message": str(e),
            "links": e.duplicates,
        }
        return _fail(session, upload_id, "duplicate", item, structured_error)
    except Exception as e:
        structured_error: GenericError = {"type": "error", "message": str(e)}
        return _fail(session, upload_id, "failed", item, structured_error)

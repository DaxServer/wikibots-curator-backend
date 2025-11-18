import json
from curator.app.commons import DuplicateUploadError, upload_file_chunked
from curator.app.crypto import decrypt_access_token
from curator.workers.celery import celery_app
from curator.app.ingest.handlers.mapillary_handler import MapillaryHandler
from curator.app.db import get_session
from curator.app.dal import (
    count_open_uploads_for_batch,
    get_upload_request_by_id,
    update_upload_status,
)


def _cleanup(session, item):
    if item:
        count_open_uploads_for_batch(
            session, userid=item.userid, batch_id=item.batch_id
        )
    session.close()


def _success(session, item, url) -> bool:
    update_upload_status(session, upload_id=item.id, status="completed", success=url)
    _cleanup(session, item)
    return True


def _fail(session, upload_id, item, structured_error: dict) -> bool:
    update_upload_status(
        session,
        upload_id=upload_id,
        status="failed",
        error=json.dumps(structured_error),
    )
    _cleanup(session, item)
    return False


@celery_app.task(name="ingest.process_one")
def process_one(upload_id: int, input: str, encrypted_access_token: str, username: str):
    session = next(get_session())
    item = None
    try:
        item = get_upload_request_by_id(session, upload_id)
        if not item:
            _cleanup(session, item)
            return False

        update_upload_status(session, upload_id=item.id, status="in_progress")

        handler = MapillaryHandler()
        image = handler.fetch_image_metadata(item.key, input)
        sdc_json = handler.build_sdc(image)
        image_url = image.url_original
        access_token = decrypt_access_token(encrypted_access_token)

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
        structured_error = {
            "type": "duplicate",
            "message": str(e),
            "links": e.duplicates,
        }
        return _fail(session, upload_id, item, structured_error)
    except Exception as e:
        structured_error = {"type": "error", "message": str(e)}
        return _fail(session, upload_id, item, structured_error)

from curator.app.models import UploadRequest
from typing import List

from curator.app.sdc import build_mapillary_sdc
from sqlalchemy.orm import Session
from mwoauth import AccessToken

from curator.app.dal import (
    count_open_uploads_for_batch,
    get_upload_request_by_id,
    update_upload_status,
)
from curator.app.commons import upload_file_chunked
from curator.app.mapillary_utils import fetch_sequence_data
from curator.workers.celery import celery_app
from curator.app.models import UploadItem
from curator.app.db import get_session


def fetch_image_metadata(image_id: str, sequence_id: str) -> dict:
    """Fetch metadata needed to build SDC for a Mapillary image id using cached sequence data."""
    print(
        f"[mapillary-worker] fetch_image_metadata: fetching metadata for image_id={image_id}, sequence_id={sequence_id}"
    )

    sequence_data = fetch_sequence_data(sequence_id)
    image_data = sequence_data.get(image_id)

    if not image_data:
        raise ValueError(f"Image data not found in sequence for image_id={image_id}")

    print(
        f"[mapillary-worker] fetch_image_metadata: got metadata for image_id={image_id}"
    )

    return image_data


def _upload_to_commons(
    item: UploadRequest,
    file_path: str,
    sdc_json: List[dict],
    access_token: AccessToken,
    username: str,
):
    return upload_file_chunked(
        filename=item.filename,
        file_path=file_path,
        wikitext=item.wikitext,
        access_token=access_token,
        username=username,
        edit_summary=f"Uploaded via Curator from Mapillary image {item.key}",
        sdc=sdc_json,
    )


def _handle_post_upload_cleanup(session: Session, userid: int, batch_id: int):
    count_open_uploads_for_batch(session, userid=userid, batch_id=batch_id)


@celery_app.task(name="mapillary.process_one")
def process_one(
    upload_id: int, sequence_id: str, access_token: AccessToken, username: str
):
    session = next(get_session())

    if not isinstance(upload_id, int):
        print(
            f"[mapillary-worker] process_one: invalid upload_id type: {type(upload_id)} value={upload_id}"
        )
        session.close()
        return False

    item: UploadRequest | None = None
    processed = False

    try:
        item = get_upload_request_by_id(session, upload_id)
        if not item:
            raise AssertionError(f"Upload request not found for id={upload_id}")
        print(
            f"[mapillary-worker] process_one: processing upload_id={item.id} sequence_id={sequence_id} image_id={item.key}"
        )

        update_upload_status(session, upload_id=item.id, status="in_progress")
        image = fetch_image_metadata(item.key, sequence_id)
        sdc_json = build_mapillary_sdc(image)
        image_url = image.get("thumb_original_url")
        if not image_url:
            raise AssertionError(
                f"Image URL not found in metadata for image_id={item.key}"
            )

        upload_result = _upload_to_commons(
            item, image_url, sdc_json, access_token, username
        )

        update_upload_status(
            session,
            upload_id=item.id,
            status="completed",
            result=str(upload_result),
        )
        processed = True

    except Exception as e:
        print(
            f"[mapillary-worker] process_one: error processing upload_id={upload_id}: {e}"
        )
        update_upload_status(
            session,
            upload_id=upload_id,
            status="failed",
            error=str(e),
        )
    finally:
        if item:
            _handle_post_upload_cleanup(session, item.userid, item.batch_id)
        session.close()

    return processed

import logging
from typing import Optional, Any
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import Session
from pydantic import BaseModel

from curator.app.db import engine
from curator.app.crypto import encrypt_access_token
from curator.app.ingest.handlers.mapillary_handler import MapillaryHandler
from curator.app.dal import (
    create_upload_request,
    get_upload_request,
    count_uploads_in_batch,
)
from curator.workers.ingest import process_one as ingest_process_one
from curator.app.auth import LoggedInUser
from curator.app.models import UploadItem


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["ws"])


class WsMessage(BaseModel):
    type: str
    data: Any = None


@router.websocket("")
async def ws(websocket: WebSocket, user: LoggedInUser):
    await websocket.accept()

    logger.info(f"User {user.get('username')} connected")

    try:
        uploads_task: Optional[asyncio.Task] = None
        while True:
            raw_data = await websocket.receive_json()
            try:
                message = WsMessage(**raw_data)
            except Exception as e:
                logger.error(f"Invalid message format: {e}")
                await websocket.send_json(
                    {"type": "ERROR", "data": "Invalid message format"}
                )
                continue

            action = message.type
            data = message.data

            logger.info(f"[ws] {action} from {user.get('username')}")

            if action == "FETCH_IMAGES":
                handler = MapillaryHandler()
                loop = asyncio.get_running_loop()
                # data is the input string
                images = await loop.run_in_executor(
                    None, handler.fetch_collection, str(data)
                )
                if not images:
                    await websocket.send_json(
                        {"type": "ERROR", "data": "Collection not found"}
                    )
                    continue

                first = next(iter(images.values()))
                creator = first.creator.model_dump()
                existing_pages = await loop.run_in_executor(
                    None,
                    handler.fetch_existing_pages,
                    [i.id for i in images.values()],
                    websocket,
                )
                for image_id, pages in existing_pages.items():
                    images[image_id].existing = pages

                def to_jsonable(x):
                    if hasattr(x, "model_dump"):
                        return x.model_dump(mode="json")
                    if isinstance(x, list):
                        return [to_jsonable(i) for i in x]
                    if isinstance(x, dict):
                        return {kk: to_jsonable(vv) for kk, vv in x.items()}
                    try:
                        d = vars(x)
                        return {kk: to_jsonable(vv) for kk, vv in d.items()}
                    except Exception:
                        return x

                img_payload = {k: to_jsonable(v) for k, v in images.items()}
                await websocket.send_json(
                    {
                        "type": "COLLECTION_IMAGES",
                        "data": {
                            "images": img_payload,
                            "creator": creator,
                        },
                    }
                )
                continue

            if action == "UPLOAD":
                # data is a dict here
                items_data = data.get("items", [])
                items = [UploadItem(**i) for i in items_data]
                handler = data.get("handler")

                with Session(engine) as session:
                    reqs = create_upload_request(
                        session=session,
                        username=user["username"],
                        userid=user["userid"],
                        payload=items,
                        handler=handler,
                    )
                    session.commit()

                    # Prepare data while session is open to avoid DetachedInstanceError
                    prepared_uploads = []
                    for i, req in enumerate(reqs):
                        session.refresh(req)
                        prepared_uploads.append(
                            {
                                "id": req.id,
                                "status": req.status,
                                "key": req.key,
                                "batchid": req.batchid,
                                "input": items[i].input,
                            }
                        )

                token = user.get("access_token")
                enc = encrypt_access_token(token) if token else None
                for upload in prepared_uploads:
                    ingest_process_one.delay(
                        upload["id"],
                        upload["input"],
                        enc,
                        user["username"],
                    )

                await websocket.send_json(
                    {
                        "type": "UPLOAD_CREATED",
                        "data": [
                            {
                                "id": u["id"],
                                "status": u["status"],
                                "image_id": u["key"],
                                "input": u["input"],
                                "batch_id": u["batchid"],
                            }
                            for u in prepared_uploads
                        ],
                    }
                )
                continue

            if action == "SUBSCRIBE_BATCH":
                # data is the batch_id (int)
                batch_id = int(data)
                if uploads_task and not uploads_task.done():
                    uploads_task.cancel()
                uploads_task = asyncio.create_task(stream_uploads(websocket, batch_id))
                await websocket.send_json({"type": "SUBSCRIBED", "data": batch_id})
                continue

            await websocket.send_json({"type": "ERROR", "data": "Unknown action"})
    except WebSocketDisconnect:
        return


async def stream_uploads(websocket: WebSocket, batch_id: int):
    try:
        while True:
            await asyncio.sleep(2)
            with Session(engine) as session:
                items = get_upload_request(
                    session,
                    batch_id=batch_id,
                    offset=0,
                    limit=1000,
                    columns=[
                        "id",
                        "status",
                        "key",
                        "batchid",
                        "error",
                        "success",
                        "handler",
                    ],
                )
                await websocket.send_json(
                    {
                        "type": "UPLOADS_UPDATE",
                        "data": [
                            {
                                "id": r.id,
                                "status": r.status,
                                "key": r.key,
                                "error": r.error,
                                "success": r.success,
                                "handler": r.handler,
                            }
                            for r in items
                        ],
                    }
                )

                total = count_uploads_in_batch(session, batch_id=batch_id)
                completed = sum(1 for r in items if r.status in ("completed", "failed"))
                if completed >= total:
                    await websocket.send_json(
                        {"type": "UPLOADS_COMPLETE", "data": batch_id}
                    )
                    break
    except WebSocketDisconnect:
        return

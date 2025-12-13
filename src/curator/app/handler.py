import logging
import asyncio
from typing import Optional, Any
from dataclasses import asdict
from curator.asyncapi import (
    BatchStats,
    FetchBatchUploadsData,
    FetchBatchesData,
    UploadData,
)
from sqlmodel import Session

from curator.app.db import engine
from curator.app.crypto import encrypt_access_token
from curator.app.ingest.handlers.mapillary_handler import MapillaryHandler
from curator.app.dal import (
    create_upload_request,
    get_upload_request,
    count_uploads_in_batch,
    get_batches,
    count_batches,
    get_batches_stats,
)
from curator.workers.ingest import process_one
from curator.workers.rq import queue as ingest_queue
from curator.app.auth import UserSession

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class Handler:
    def __init__(self, user: UserSession, sender: WebSocket, request_obj: Any):
        self.user = user
        self.socket = sender
        self.request_obj = (
            request_obj  # Can be WebSocket or Request, needed for WcqsSession
        )
        self.uploads_task: Optional[asyncio.Task] = None

    def cancel_tasks(self):
        if self.uploads_task and not self.uploads_task.done():
            self.uploads_task.cancel()

    async def fetch_images(self, collection: str):
        handler = MapillaryHandler()
        loop = asyncio.get_running_loop()
        # data is the input string
        images = await handler.fetch_collection(collection)
        if not images:
            logger.error(
                f"[ws] [resp] Collection not found for {collection} for {self.user.get('username')}"
            )
            await self.socket.send_json(
                {"type": "ERROR", "data": "Collection not found"}
            )
            return

        first = next(iter(images.values()))
        creator = first.creator.model_dump()

        # We pass self.request_obj because fetch_existing_pages expects Union[Request, WebSocket]
        # to initialize WcqsSession
        existing_pages = await loop.run_in_executor(
            None,
            handler.fetch_existing_pages,
            [i.id for i in images.values()],
            self.request_obj,
        )
        for image_id, pages in existing_pages.items():
            images[image_id].existing = pages

        img_payload = {k: v.model_dump(mode="json") for k, v in images.items()}

        logger.info(
            f"[ws] [resp] Sending collection {collection} images for {self.user.get('username')}"
        )
        await self.socket.send_json(
            {
                "type": "COLLECTION_IMAGES",
                "data": {
                    "images": img_payload,
                    "creator": creator,
                },
            }
        )

    async def upload(self, data: UploadData):
        items = data.items
        handler_name = data.handler
        encrypted_access_token = encrypt_access_token(self.user.get("access_token"))

        with Session(engine) as session:
            reqs = create_upload_request(
                session=session,
                username=self.user["username"],
                userid=self.user["userid"],
                payload=items,
                handler=handler_name,
                encrypted_access_token=encrypted_access_token,
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

        for upload in prepared_uploads:
            ingest_queue.enqueue(
                process_one,
                upload["id"],
            )

        logger.info(
            f"[ws] [resp] Batch uploads {len(prepared_uploads)} created for {handler_name} for {self.user.get('username')}"
        )
        await self.socket.send_json(
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

    async def fetch_batches(self, data: FetchBatchesData):
        page = data.page
        limit = data.limit
        userid = data.userid
        offset = (page - 1) * limit

        with Session(engine) as session:
            batches = get_batches(session, userid, offset, limit)
            total = count_batches(session, userid)

            batch_ids = [b.id for b in batches]
            stats = get_batches_stats(session, batch_ids)

            # Serialize manually to handle relationships and specific fields
            serialized_batches = []
            for batch in batches:
                b_dict = {
                    "id": batch.id,
                    "created_at": batch.created_at.isoformat(),
                    "username": batch.user.username,
                    "userid": batch.userid,
                    "stats": asdict(
                        stats.get(
                            batch.id,
                            BatchStats(
                                total=1,
                                queued=0,
                                in_progress=0,
                                completed=0,
                                failed=0,
                            ),
                        )
                    ),
                }
                serialized_batches.append(b_dict)

        logger.info(
            f"[ws] [resp] Sending {len(serialized_batches)} batches for {self.user.get('username')}"
        )
        await self.socket.send_json(
            {
                "type": "BATCHES_LIST",
                "data": {
                    "items": serialized_batches,
                    "total": total,
                },
            }
        )

    async def fetch_batch_uploads(self, data: FetchBatchUploadsData):
        batch_id = data.batch_id

        with Session(engine) as session:
            uploads = get_upload_request(
                session,
                batch_id,
                columns=[
                    "id",
                    "batchid",
                    "status",
                    "key",
                    "error",
                    "success",
                    "handler",
                    "filename",
                    "wikitext",
                ],
            )
            serialized_uploads = []

            for upload in uploads:
                u_dict = upload.model_dump(mode="json")
                u_dict["image_id"] = upload.key
                serialized_uploads.append(u_dict)

        logger.info(
            f"[ws] [resp] Sending {len(serialized_uploads)} uploads for batch {batch_id} for {self.user.get('username')}"
        )
        await self.socket.send_json(
            {
                "type": "BATCH_UPLOADS_LIST",
                "data": serialized_uploads,
            }
        )

    async def subscribe_batch(self, batch_id: int):
        if self.uploads_task and not self.uploads_task.done():
            self.uploads_task.cancel()

        self.uploads_task = asyncio.create_task(self.stream_uploads(batch_id))

        logger.info(
            f"[ws] [resp] Subscribed to batch {batch_id} for {self.user.get('username')}"
        )
        await self.socket.send_json({"type": "SUBSCRIBED", "data": batch_id})

    async def stream_uploads(self, batch_id: int):
        try:
            while True:
                await asyncio.sleep(2)
                with Session(engine) as session:
                    items = get_upload_request(
                        session,
                        batch_id=batch_id,
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
                    logger.info(
                        f"[ws] [resp] Sending batch {batch_id} update for {self.user.get('username')}"
                    )
                    await self.socket.send_json(
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
                    completed = sum(
                        1 for r in items if r.status in ("completed", "failed")
                    )
                    if completed >= total:
                        logger.info(
                            f"[ws] [resp] Batch {batch_id} completed for {self.user.get('username')}"
                        )
                        await self.socket.send_json(
                            {"type": "UPLOADS_COMPLETE", "data": batch_id}
                        )
                        break
        except (asyncio.CancelledError, WebSocketDisconnect):
            # Task cancelled or client disconnected, just exit
            return
        except Exception as e:
            logger.error(f"Error in stream_uploads: {e}")

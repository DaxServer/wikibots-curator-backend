import logging
import asyncio
from typing import Optional, Any, Protocol
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
)
from curator.workers.ingest import process_one as ingest_process_one
from curator.app.messages import (
    UploadData,
    FetchBatchesPayload,
    FetchBatchUploadsPayload,
)
from curator.app.auth import UserSession

from fastapi import WebSocketDisconnect

logger = logging.getLogger(__name__)


class WebSocketSender(Protocol):
    async def send_json(self, data: Any) -> None: ...


class Handler:
    def __init__(self, user: UserSession, sender: WebSocketSender, request_obj: Any):
        self.user = user
        self.sender = sender
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
        images = await loop.run_in_executor(None, handler.fetch_collection, collection)
        if not images:
            logger.error(
                f"[ws] [resp] Collection not found for {collection} for {self.user.get('username')}"
            )
            await self.sender.send_json(
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
        await self.sender.send_json(
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

        with Session(engine) as session:
            reqs = create_upload_request(
                session=session,
                username=self.user["username"],
                userid=self.user["userid"],
                payload=items,
                handler=handler_name,
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

        token = self.user.get("access_token")
        enc = encrypt_access_token(token) if token else None
        for upload in prepared_uploads:
            ingest_process_one.delay(
                upload["id"],
                upload["input"],
                enc,
                self.user["username"],
            )

        logger.info(
            f"[ws] [resp] Batch uploads {len(prepared_uploads)} created for {handler_name} for {self.user.get('username')}"
        )
        await self.sender.send_json(
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

    async def fetch_batches(self, data: FetchBatchesPayload):
        page = data.page
        limit = data.limit
        userid = data.userid
        offset = (page - 1) * limit

        with Session(engine) as session:
            batches = get_batches(session, userid, offset, limit)
            total = count_batches(session, userid)

            # Serialize manually to handle relationships and specific fields
            serialized_batches = []
            for batch in batches:
                b_dict = {
                    "id": batch.id,
                    "created_at": batch.created_at.isoformat(),
                    "username": batch.user.username,
                    "userid": batch.userid,
                    "uploads": [
                        {
                            "success": u.success,
                            "error": u.error,
                            "status": u.status,
                        }
                        for u in batch.uploads
                    ],
                }
                serialized_batches.append(b_dict)

        logger.info(
            f"[ws] [resp] Sending {len(serialized_batches)} batches for {self.user.get('username')}"
        )
        await self.sender.send_json(
            {
                "type": "BATCHES_LIST",
                "data": {
                    "items": serialized_batches,
                    "total": total,
                },
            }
        )

    async def fetch_batch_uploads(self, data: FetchBatchUploadsPayload):
        batch_id = data.batch_id
        page = data.page
        limit = data.limit
        columns_str = data.columns
        columns = columns_str.split(",") if columns_str else None
        offset = (page - 1) * limit

        # Ensure 'key' is requested if we use load_only, because we map it to image_id
        dal_columns = list(columns) if columns else None
        if dal_columns and "key" not in dal_columns:
            dal_columns.append("key")

        with Session(engine) as session:
            uploads = get_upload_request(session, batch_id, offset, limit, dal_columns)
            total = count_uploads_in_batch(session, batch_id)

            serialized_uploads = []

            # If columns were requested, we should try to respect them in the output to save serialization time
            # But we must include 'key' for image_id mapping.
            include_fields = set(columns) if columns else None
            if include_fields:
                include_fields.add("key")

            for upload in uploads:
                u_dict = upload.model_dump(mode="json", include=include_fields)
                u_dict["image_id"] = upload.key
                serialized_uploads.append(u_dict)

        logger.info(
            f"[ws] [resp] Sending {len(serialized_uploads)} uploads for batch {batch_id} for {self.user.get('username')}"
        )
        await self.sender.send_json(
            {
                "type": "BATCH_UPLOADS_LIST",
                "data": {
                    "items": serialized_uploads,
                    "total": total,
                },
            }
        )

    async def subscribe_batch(self, batch_id: int):
        if self.uploads_task and not self.uploads_task.done():
            self.uploads_task.cancel()

        self.uploads_task = asyncio.create_task(self.stream_uploads(batch_id))

        logger.info(
            f"[ws] [resp] Subscribed to batch {batch_id} for {self.user.get('username')}"
        )
        await self.sender.send_json({"type": "SUBSCRIBED", "data": batch_id})

    async def stream_uploads(self, batch_id: int):
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
                    logger.info(
                        f"[ws] [resp] Sending batch {batch_id} update for {self.user.get('username')}"
                    )
                    await self.sender.send_json(
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
                        await self.sender.send_json(
                            {"type": "UPLOADS_COMPLETE", "data": batch_id}
                        )
                        break
        except (asyncio.CancelledError, WebSocketDisconnect):
            # Task cancelled or client disconnected, just exit
            return
        except Exception as e:
            logger.error(f"Error in stream_uploads: {e}")

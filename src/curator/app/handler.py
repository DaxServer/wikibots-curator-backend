import asyncio
import logging
from typing import Any, Optional, cast

import httpx
from fastapi import WebSocketDisconnect
from rq import Queue

from curator.app.auth import UserSession
from curator.app.crypto import encrypt_access_token
from curator.app.dal import (
    count_uploads_in_batch,
    create_upload_request,
    get_batch,
    get_upload_request,
    reset_failed_uploads,
)
from curator.app.db import get_session
from curator.app.handler_optimized import OptimizedBatchStreamer
from curator.app.handlers.mapillary_handler import MapillaryHandler
from curator.app.models import UploadItem
from curator.asyncapi import (
    BatchUploadsListData,
    CollectionImagesData,
    FetchBatchesData,
    SubscribeBatchesListData,
    UploadCreatedItem,
    UploadData,
    UploadUpdateItem,
)
from curator.protocol import AsyncAPIWebSocket
from curator.workers.ingest import process_one
from curator.workers.rq import queue as ingest_queue

logger = logging.getLogger(__name__)


class Handler:
    def __init__(self, user: UserSession, sender: AsyncAPIWebSocket, request_obj: Any):
        self.user = user
        self.socket = sender
        self.request_obj = (
            request_obj  # Can be WebSocket or Request, needed for WcqsSession
        )
        self.uploads_task: Optional[asyncio.Task] = None
        self.batches_list_task: Optional[asyncio.Task] = None
        self.batch_streamer = OptimizedBatchStreamer(sender, user.get("username"))

    def cancel_tasks(self):
        if self.uploads_task and not self.uploads_task.done():
            self.uploads_task.cancel()
        if self.batches_list_task and not self.batches_list_task.done():
            self.batches_list_task.cancel()
        if self.batch_streamer:
            asyncio.create_task(self.batch_streamer.stop_streaming())

    async def fetch_images(self, collection: str):
        handler = MapillaryHandler()
        loop = asyncio.get_running_loop()
        try:
            images = await handler.fetch_collection(collection)
        except httpx.HTTPStatusError as e:
            logger.error(
                f"[ws] [resp] Mapillary API error for {collection} for {self.user.get('username')}: {e}"
            )
            await self.socket.send_error(f"Mapillary API Error: {e.response.text}")
            return

        if not images:
            logger.error(
                f"[ws] [resp] Collection not found for {collection} for {self.user.get('username')}"
            )
            await self.socket.send_error("Collection not found")
            return

        first = next(iter(images.values()))
        creator = first.creator

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

        logger.info(
            f"[ws] [resp] Sending collection {collection} images for {self.user.get('username')}"
        )
        await self.socket.send_collection_images(
            CollectionImagesData(images=images, creator=creator)
        )

    async def upload(self, data: UploadData):
        items = data.items
        handler_name = data.handler
        encrypted_access_token = encrypt_access_token(self.user.get("access_token"))

        with next(get_session()) as session:
            reqs = create_upload_request(
                session=session,
                username=self.user["username"],
                userid=self.user["userid"],
                payload=cast(list[UploadItem], items),
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

        ingest_queue.enqueue_many(
            [
                Queue.prepare_data(process_one, (upload["id"],))
                for upload in prepared_uploads
            ]
        )

        logger.info(
            f"[ws] [resp] Batch uploads {len(prepared_uploads)} created for {handler_name} for {self.user.get('username')}"
        )
        await self.socket.send_upload_created(
            [
                UploadCreatedItem(
                    id=u["id"],
                    status=u["status"],
                    image_id=u["key"],
                    input=u["input"],
                    batchid=u["batchid"],
                )
                for u in prepared_uploads
            ]
        )

    async def fetch_batches(self, data: FetchBatchesData):
        """Fetch batches and automatically subscribe to updates."""
        if self.batches_list_task and not self.batches_list_task.done():
            self.batches_list_task.cancel()

        if self.batch_streamer:
            await self.batch_streamer.stop_streaming()

        # Start the optimized streamer which will send initial full sync and then partial updates
        self.batches_list_task = asyncio.create_task(
            self.batch_streamer.start_streaming(
                data.userid, data.filter, page=data.page, limit=data.limit
            )
        )

        logger.info(
            f"[ws] [resp] FetchBatches and subscribed to batches list for {self.user.get('username')}"
        )

    async def fetch_batch_uploads(self, batchid: int):
        with next(get_session()) as session:
            batch = get_batch(session, batchid)
            if not batch:
                await self.socket.send_error(f"Batch {batchid} not found")
                return

            serialized_uploads = get_upload_request(
                session,
                batchid,
            )

        logger.info(
            f"[ws] [resp] Sending batch {batchid} and {len(serialized_uploads)} uploads for {self.user.get('username')}"
        )
        await self.socket.send_batch_uploads_list(
            BatchUploadsListData(batch=batch, uploads=serialized_uploads)
        )

    async def retry_uploads(self, batchid: int):
        username = self.user["username"]
        userid = self.user["userid"]
        encrypted_access_token = encrypt_access_token(self.user.get("access_token"))

        try:
            with next(get_session()) as session:
                retried_ids = reset_failed_uploads(
                    session, batchid, userid, encrypted_access_token
                )
        except ValueError:
            await self.socket.send_error(f"Batch {batchid} not found")
            return
        except PermissionError:
            await self.socket.send_error("Permission denied")
            return

        if not retried_ids:
            logger.info(
                f"[ws] [resp] No failed uploads to retry for batch {batchid} for {username}"
            )
            await self.socket.send_error("No failed uploads to retry")
            return

        ingest_queue.enqueue_many(
            [Queue.prepare_data(process_one, (uid,)) for uid in retried_ids]
        )

        logger.info(
            f"[ws] [resp] Retried {len(retried_ids)} uploads for batch {batchid} for {username}"
        )

    async def subscribe_batch(self, batchid: int):
        if self.uploads_task and not self.uploads_task.done():
            self.uploads_task.cancel()

        self.uploads_task = asyncio.create_task(self.stream_uploads(batchid))

        logger.info(
            f"[ws] [resp] Subscribed to batch {batchid} for {self.user.get('username')}"
        )
        await self.socket.send_subscribed(batchid)

    async def unsubscribe_batch(self):
        if self.uploads_task and not self.uploads_task.done():
            self.uploads_task.cancel()

        logger.info(
            f"[ws] [resp] Unsubscribed from batch updates for {self.user.get('username')}"
        )

    async def stream_uploads(self, batchid: int):
        last_update_items = None
        try:
            while True:
                await asyncio.sleep(2)

                with next(get_session()) as session:
                    items = get_upload_request(
                        session,
                        batchid=batchid,
                    )

                    update_items = [
                        UploadUpdateItem(
                            id=item.id,
                            batchid=batchid,
                            status=item.status,
                            key=item.key or "unknown",
                            handler=item.handler or "unknown",
                            error=item.error,
                            success=item.success,
                        )
                        for item in items
                    ]

                    if update_items != last_update_items:
                        logger.info(
                            f"[ws] [resp] Sending batch {batchid} update for {self.user.get('username')}"
                        )
                        await self.socket.send_uploads_update(update_items)
                        last_update_items = update_items

                    total = count_uploads_in_batch(session, batchid=batchid)
                    completed = sum(
                        1
                        for r in items
                        if r.status in ("completed", "failed", "duplicate")
                    )
                    if completed >= total:
                        logger.info(
                            f"[ws] [resp] Batch {batchid} completed for {self.user.get('username')}"
                        )
                        await self.socket.send_uploads_complete(batchid)
                        break
        except (asyncio.CancelledError, WebSocketDisconnect):
            # Task cancelled or client disconnected, just exit
            return
        except Exception as e:
            logger.error(f"Error in stream_uploads: {e}")

    async def subscribe_batches_list(self, data: SubscribeBatchesListData):
        """Deprecated: Subscription is now automatic in fetch_batches."""
        if self.batches_list_task and not self.batches_list_task.done():
            self.batches_list_task.cancel()

        if self.batch_streamer:
            await self.batch_streamer.stop_streaming()

        self.batches_list_task = asyncio.create_task(
            self.batch_streamer.start_streaming(
                data.userid, data.filter, page=1, limit=100
            )
        )

        logger.info(
            f"[ws] [resp] Subscribed to batches list for {self.user.get('username')}"
        )

    async def unsubscribe_batches_list(self):
        if self.batches_list_task and not self.batches_list_task.done():
            self.batches_list_task.cancel()

        if self.batch_streamer:
            await self.batch_streamer.stop_streaming()

        logger.info(
            f"[ws] [resp] Unsubscribed from batches list for {self.user.get('username')}"
        )

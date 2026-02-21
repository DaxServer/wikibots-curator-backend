import asyncio
import functools
import logging
from datetime import datetime
from typing import Any, Optional, cast

import httpx
from fastapi import WebSocketDisconnect
from sqlmodel import Session

from curator.app.auth import UserSession
from curator.app.config import QueuePriority
from curator.app.crypto import (
    decrypt_access_token,
    encrypt_access_token,
)
from curator.app.dal import (
    cancel_batch,
    count_batches,
    count_uploads_in_batch,
    create_batch,
    create_upload_requests_for_batch,
    ensure_user,
    get_batch,
    get_batch_ids_with_recent_changes,
    get_batches,
    get_batches_minimal,
    get_latest_update_time,
    get_upload_request,
    reset_failed_uploads_to_new_batch,
)
from curator.app.db import get_session
from curator.app.models import Batch, UploadItem
from curator.app.task_enqueuer import enqueue_uploads
from curator.asyncapi import (
    BatchesListData,
    BatchUploadsListData,
    CollectionImagesData,
    DuplicatedSdcNotUpdatedError,
    DuplicatedSdcUpdatedError,
    DuplicateError,
    FetchBatchesData,
    ImageHandler,
    MediaImage,
    PartialCollectionImagesData,
    SubscribeBatchesListData,
    UploadSliceAckItem,
    UploadSliceData,
    UploadUpdateItem,
)
from curator.handlers.flickr_handler import FlickrHandler
from curator.handlers.interfaces import Handler as BaseHandler
from curator.handlers.mapillary_handler import MapillaryHandler
from curator.protocol import AsyncAPIWebSocket
from curator.workers.celery import app as celery_app

logger = logging.getLogger(__name__)


def get_handler_for_handler_type(
    handler: ImageHandler,
) -> FlickrHandler | MapillaryHandler:
    """Return the appropriate handler based on ImageHandler enum"""
    if handler == ImageHandler.FLICKR:
        return FlickrHandler()
    return MapillaryHandler()


def handle_exceptions(func):
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except WebSocketDisconnect:
            raise  # Let the main loop handle disconnects
        except Exception as e:
            logger.exception(f"Error in {func.__name__} for user {self.username}: {e}")
            await self.socket.send_error(
                "Internal server error.. please notify User:DaxServer"
            )

    return wrapper


class Handler:
    def __init__(self, user: UserSession, sender: AsyncAPIWebSocket, request_obj: Any):
        self.user = user
        self.username = user.get("username")
        self.socket = sender
        self.request_obj = (
            request_obj  # Can be WebSocket or Request, needed for WcqsSession
        )
        self.uploads_task: Optional[asyncio.Task] = None
        self.batches_list_task: Optional[asyncio.Task] = None
        self.batch_streamer = OptimizedBatchStreamer(sender, self.username)

    def cancel_tasks(self):
        if self.uploads_task and not self.uploads_task.done():
            self.uploads_task.cancel()
        if self.batches_list_task and not self.batches_list_task.done():
            self.batches_list_task.cancel()
        if self.batch_streamer:
            asyncio.create_task(self.batch_streamer.stop_streaming())

    @handle_exceptions
    async def fetch_images(self, collection: str, handler_type: ImageHandler):
        handler = get_handler_for_handler_type(handler_type)
        loop = asyncio.get_running_loop()

        try:
            images = await handler.fetch_collection(collection)
        except httpx.ReadTimeout:
            logger.error(
                f"[{handler.name}] API timeout for {collection} for {self.username}"
            )
            await self._fetch_images_in_batches(collection, handler, loop)
            return
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 500:
                await self._fetch_images_in_batches(collection, handler, loop)
                return

            logger.error(
                f"[{handler.name}] API error for {collection} for {self.username}: {e}"
            )
            await self.socket.send_error(
                f"{handler.name.title()} API Error: {e.response.text}"
            )
            return

        if not images:
            logger.error(
                f"[{handler.name}] Collection not found for {collection} for {self.username}"
            )
            await self.socket.send_error("Collection not found")
            return

        await self._send_full_collection(collection, images, handler, loop)

    async def _fetch_images_in_batches(
        self,
        collection: str,
        handler: BaseHandler,
        loop: asyncio.AbstractEventLoop,
    ):
        logger.warning(
            f"[{handler.name}] Attempting batch retrieval for {collection} for {self.username}"
        )
        await self.socket.send_try_batch_retrieval(
            "Large collection detected. Loading in batches..."
        )

        try:
            ids = await handler.fetch_collection_ids(collection)
            logger.info(
                f"[{handler.name}] Found {len(ids)} images in collection {collection} for {self.username}"
            )

            if not ids:
                await self.socket.send_error("Collection has no images")
                return

            await self.socket.send_collection_image_ids(ids)

            # Process in batches
            for i in range(0, len(ids), 100):
                batch_ids = ids[i : i + 100]
                batch_images = await handler.fetch_images_batch(batch_ids, collection)

                existing_pages = await loop.run_in_executor(
                    None,
                    handler.fetch_existing_pages,
                    list(batch_images.keys()),
                    self.request_obj,
                )
                for image_id, pages in existing_pages.items():
                    batch_images[image_id].existing = pages

                await self.socket.send_partial_collection_images(
                    PartialCollectionImagesData(
                        images=list(batch_images.values()),
                        collection=collection,
                    )
                )
        except WebSocketDisconnect:
            logger.info(
                f"[{handler.name}] User {self.username} disconnected during batch retrieval for {collection}"
            )
            pass
        except Exception as ex:
            logger.error(
                f"[{handler.name}] Batch retrieval failed for {collection}: {ex}"
            )
            await self.socket.send_error(f"Batch retrieval failed: {ex}")

    async def _send_full_collection(
        self,
        collection: str,
        images: dict[str, MediaImage],
        handler: BaseHandler,
        loop: asyncio.AbstractEventLoop,
    ):
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
            f"[{handler.name}] Sending collection {collection} images for {self.username}"
        )
        await self.socket.send_collection_images(
            CollectionImagesData(images=images, creator=creator)
        )

    @handle_exceptions
    async def create_batch(self):
        with get_session() as session:
            ensure_user(
                session=session, userid=self.user["userid"], username=self.username
            )
            batch = create_batch(
                session=session, userid=self.user["userid"], username=self.username
            )
            batch_id = batch.id

        logger.info(f"[ws] [resp] Batch {batch_id} created for {self.username}")
        await self.socket.send_batch_created(batch_id)

    @handle_exceptions
    async def upload_slice(
        self,
        data: UploadSliceData,
        priority: Optional[QueuePriority] = QueuePriority.NORMAL,
    ):
        batchid = data.batchid
        items = data.items
        handler_name = data.handler
        sliceid = data.sliceid
        encrypted_access_token = encrypt_access_token(self.user.get("access_token"))

        logger.info(
            f"[mapillary] Creating upload slice {sliceid} with {len(items)} items for {self.username} in batch {batchid}"
        )

        with get_session() as session:
            # Fetch batch to get its edit_group_id
            batch = session.get(Batch, batchid)
            if not batch:
                await self.socket.send_error(f"Batch {batchid} not found")
                return

            edit_group_id = batch.edit_group_id
            if not edit_group_id:
                await self.socket.send_error(f"Batch {batchid} has no edit_group_id")
                return

            reqs = create_upload_requests_for_batch(
                session=session,
                userid=self.user["userid"],
                username=self.username,
                batchid=batchid,
                payload=cast(list[UploadItem], items),
                handler=handler_name,
                encrypted_access_token=encrypted_access_token,
            )

            prepared_uploads: dict[str, str] = {}
            to_enqueue = []
            for req in reqs:
                session.refresh(req)
                prepared_uploads[req.key] = req.status
                to_enqueue.append(req.id)

        # Enqueue uploads with rate limit spacing
        access_token = self.user.get("access_token")
        await enqueue_uploads(
            upload_ids=to_enqueue,
            edit_group_id=edit_group_id,
            userid=self.user["userid"],
            access_token=access_token,
        )

        logger.info(
            f"[ws] [resp] Slice {sliceid} of batch {batchid} ({len(to_enqueue)} uploads) enqueued for {self.username}"
        )

        await self.socket.send_upload_slice_ack(
            data=[
                UploadSliceAckItem(id=key, status=status)
                for key, status in prepared_uploads.items()
            ],
            sliceid=sliceid,
        )

    @handle_exceptions
    async def fetch_batches(self, data: FetchBatchesData):
        """Fetch batches and automatically subscribe to updates"""
        if self.batches_list_task and not self.batches_list_task.done():
            self.batches_list_task.cancel()
            try:
                await self.batches_list_task
            except asyncio.CancelledError:
                pass

        # Reset the streamer state for a fresh fetch
        self.batch_streamer = OptimizedBatchStreamer(self.socket, self.username)

        # Start the optimized streamer which will send initial full sync and then partial updates
        self.batches_list_task = asyncio.create_task(
            self.batch_streamer.start_streaming(
                data.userid, data.filter, page=data.page, limit=data.limit
            )
        )

        logger.info(
            f"[ws] [resp] FetchBatches and subscribed to batches list for {self.username}"
        )

    @handle_exceptions
    async def fetch_batch_uploads(self, batchid: int):
        with get_session() as session:
            batch = get_batch(session, batchid)
            if not batch:
                await self.socket.send_error(f"Batch {batchid} not found")
                return

            serialized_uploads = get_upload_request(
                session,
                batchid,
            )

        logger.info(
            f"[ws] [resp] Sending batch {batchid} and {len(serialized_uploads)} uploads for {self.username}"
        )
        await self.socket.send_batch_uploads_list(
            BatchUploadsListData(batch=batch, uploads=serialized_uploads)
        )

    @handle_exceptions
    async def retry_uploads(
        self, batchid: int, priority: Optional[QueuePriority] = QueuePriority.NORMAL
    ):
        userid = self.user["userid"]
        encrypted_access_token = encrypt_access_token(self.user.get("access_token"))

        try:
            with get_session() as session:
                retried_ids, edit_group_id = reset_failed_uploads_to_new_batch(
                    session, batchid, userid, encrypted_access_token, self.username
                )
        except ValueError:
            await self.socket.send_error(f"Batch {batchid} not found")
            return
        except PermissionError:
            await self.socket.send_error("Permission denied")
            return

        if not retried_ids or not edit_group_id:
            logger.info(
                f"[ws] [resp] No failed uploads to retry for batch {batchid} for {self.username}"
            )
            await self.socket.send_error("No failed uploads to retry")
            return

        # Enqueue retries with new batch's edit_group_id
        access_token = decrypt_access_token(encrypted_access_token)
        await enqueue_uploads(
            upload_ids=retried_ids,
            edit_group_id=edit_group_id,
            userid=self.user["userid"],
            access_token=access_token,
        )

        logger.info(
            f"[ws] [resp] Retried {len(retried_ids)} uploads for batch {batchid} for {self.username}"
        )

    @handle_exceptions
    async def cancel_batch(self, batchid: int):
        is_admin = self.username == "DaxServer"
        userid = None if is_admin else self.user["userid"]

        try:
            with get_session() as session:
                cancelled_task_ids = cancel_batch(session, batchid, userid)
        except ValueError:
            await self.socket.send_error(f"Batch {batchid} not found")
            return
        except PermissionError:
            await self.socket.send_error("Permission denied")
            return

        if not cancelled_task_ids:
            logger.info(
                f"[ws] [resp] No queued items to cancel for batch {batchid} for {self.username}"
            )
            await self.socket.send_error("No queued items to cancel")
            return

        revoke_celery_tasks_by_id(cancelled_task_ids)

        logger.info(
            f"[ws] [resp] Cancelled {len(cancelled_task_ids)} uploads for batch {batchid} for {self.username}"
        )

    @handle_exceptions
    async def subscribe_batch(self, batchid: int):
        if self.uploads_task and not self.uploads_task.done():
            self.uploads_task.cancel()

        self.uploads_task = asyncio.create_task(self.stream_uploads(batchid))

        logger.info(f"[ws] [resp] Subscribed to batch {batchid} for {self.username}")
        await self.socket.send_subscribed(batchid)

    @handle_exceptions
    async def unsubscribe_batch(self):
        if self.uploads_task and not self.uploads_task.done():
            self.uploads_task.cancel()

        logger.info(f"[ws] [resp] Unsubscribed from batch updates for {self.username}")

    async def stream_uploads(self, batchid: int):
        last_update_items = None
        try:
            while True:
                await asyncio.sleep(2)

                with get_session() as session:
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
                            f"[ws] [resp] Sending batch {batchid} update for {self.username}"
                        )
                        await self.socket.send_uploads_update(update_items)
                        last_update_items = update_items

                    total = count_uploads_in_batch(session, batchid=batchid)
                    completed = sum(
                        1
                        for r in items
                        if r.status
                        in (
                            "completed",
                            "failed",
                            DuplicateError.model_fields["type"].default,
                            DuplicatedSdcUpdatedError.model_fields["type"].default,
                            DuplicatedSdcNotUpdatedError.model_fields["type"].default,
                        )
                    )
                    if completed >= total:
                        logger.info(
                            f"[ws] [resp] Batch {batchid} completed for {self.username}"
                        )
                        await self.socket.send_uploads_complete(batchid)
                        break
        except (asyncio.CancelledError, WebSocketDisconnect):
            logger.info(
                f"[ws] [resp] Disconnected while streaming batch {batchid} for {self.username}"
            )
            return
        except Exception as e:
            logger.error(f"Error in stream_uploads: {e}")

    @handle_exceptions
    async def subscribe_batches_list(self, data: SubscribeBatchesListData):
        """Deprecated: Subscription is now automatic in fetch_batches."""
        if self.batches_list_task and not self.batches_list_task.done():
            self.batches_list_task.cancel()
            try:
                await self.batches_list_task
            except asyncio.CancelledError:
                pass

        self.batch_streamer = OptimizedBatchStreamer(self.socket, self.username)

        self.batches_list_task = asyncio.create_task(
            self.batch_streamer.start_streaming(
                data.userid, data.filter, page=1, limit=100
            )
        )

        logger.info(f"[ws] [resp] Subscribed to batches list for {self.username}")

    @handle_exceptions
    async def unsubscribe_batches_list(self):
        if self.batches_list_task and not self.batches_list_task.done():
            self.batches_list_task.cancel()
            try:
                await self.batches_list_task
            except asyncio.CancelledError:
                pass

        if self.batch_streamer:
            await self.batch_streamer.stop_streaming()

        logger.info(f"[ws] [resp] Unsubscribed from batches list for {self.username}")


def revoke_celery_tasks_by_id(upload_task_ids: dict[int, str]) -> dict[int, bool]:
    """Revoke Celery tasks for the given upload IDs using their stored task IDs"""
    results = {}
    for upload_id, task_id in upload_task_ids.items():
        try:
            if not task_id:
                logger.warning(
                    f"No task ID for upload {upload_id}, skipping revocation"
                )
                results[upload_id] = False
                continue
            celery_app.control.revoke(task_id, terminate=False)
            results[upload_id] = True
        except Exception as e:
            logger.warning(
                f"Failed to revoke task {task_id} for upload {upload_id}: {e}"
            )
            results[upload_id] = False

    return results


class OptimizedBatchStreamer:
    """Optimized batch streaming with intelligent updates and reduced payload size."""

    def __init__(self, socket: AsyncAPIWebSocket, username: str):
        self.socket = socket
        self.username = username
        self.last_update_time: Optional[datetime] = None
        self.is_running = False
        self.page = 1
        self.limit = 100

    async def start_streaming(
        self,
        userid: Optional[str] = None,
        filter_text: Optional[str] = None,
        page: int = 1,
        limit: int = 100,
        update_check_interval: int = 2,
    ):
        """Start optimized batch streaming with intelligent updates."""
        self.is_running = True
        self.page = page
        self.limit = limit
        logger.info(
            f"[ws] [resp] Starting optimized batch streaming for {self.username} (page: {page}, limit: {limit})"
        )

        try:
            with get_session() as session:
                await self._send_full_sync(session, userid, filter_text)
                self.last_update_time = get_latest_update_time(
                    session, userid, filter_text
                )

            if self.page > 1:
                logger.info(
                    f"[ws] [resp] Pagination detected (page {self.page}), not streaming updates for {self.username}"
                )
                return

            while self.is_running:
                await asyncio.sleep(update_check_interval)

                with get_session() as session:
                    current_latest = get_latest_update_time(
                        session, userid, filter_text
                    )

                    if current_latest and (
                        self.last_update_time is None
                        or current_latest > self.last_update_time
                    ):
                        logger.info(
                            f"[ws] [resp] Updates detected for {self.username}, sending incremental update"
                        )
                        check_time = self.last_update_time or datetime.min
                        await self._send_incremental_updates(
                            session, userid, filter_text, check_time
                        )
                        self.last_update_time = current_latest

        except asyncio.CancelledError:
            logger.info(
                f"[ws] [resp] Stopping optimized batch streaming for {self.username}"
            )
        except Exception as e:
            logger.error(f"[ws] [resp] Error in optimized batch streaming: {e}")
            raise

    async def stop_streaming(self):
        """Stop the streaming process."""
        if self.is_running:
            self.is_running = False
            logger.info(
                f"[ws] [resp] Stopped optimized batch streaming for {self.username}"
            )

    async def _send_full_sync(
        self, session: Session, userid: Optional[str], filter_text: Optional[str]
    ):
        """Send a full sync of all batches."""
        offset = (self.page - 1) * self.limit
        batch_items = get_batches(session, userid, offset, self.limit, filter_text)
        total_count = count_batches(session, userid, filter_text)
        current_data = BatchesListData(items=batch_items, total=total_count)

        await self.socket.send_batches_list(current_data, partial=False)

        logger.info(
            f"[ws] [resp] Full sync completed for {self.username}: sent {len(batch_items)} batches (total: {total_count})"
        )

    async def _send_incremental_updates(
        self,
        session: Session,
        userid: Optional[str],
        filter_text: Optional[str],
        last_update_time: datetime,
    ):
        """Send only batches that have changed recently."""
        changed_batch_ids = get_batch_ids_with_recent_changes(
            session, last_update_time, userid, filter_text
        )

        if not changed_batch_ids:
            return

        changed_batches = get_batches_minimal(session, changed_batch_ids)

        if not changed_batches:
            return

        total_count = count_batches(session, userid, filter_text)

        update_data = BatchesListData(items=changed_batches, total=total_count)

        await self.socket.send_batches_list(update_data, partial=True)

        logger.info(
            f"[ws] [resp] Sent incremental update for {self.username}: {len(changed_batches)} batches (total: {total_count})"
        )

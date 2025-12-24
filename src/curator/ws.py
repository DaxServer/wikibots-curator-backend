import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from curator.app.auth import LoggedInUser
from curator.app.handler import Handler
from curator.asyncapi import (
    FetchBatches,
    FetchBatchUploads,
    FetchImages,
    RetryUploads,
    SubscribeBatch,
    SubscribeBatchesList,
    UnsubscribeBatch,
    UnsubscribeBatchesList,
    Upload,
)
from curator.protocol import (
    WS_CHANNEL_ADDRESS,
    AsyncAPIWebSocket,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ws"])


@router.websocket(WS_CHANNEL_ADDRESS)
async def ws(websocket: WebSocket, user: LoggedInUser):
    # Wrap the standard WebSocket with our typed version
    typed_ws = AsyncAPIWebSocket(websocket.scope, websocket.receive, websocket.send)
    await typed_ws.accept()

    logger.info(f"User {user.get('username')} connected")

    # Create the logic handler
    # websocket acts as both sender and request object (for WcqsSession)
    handler = Handler(user=user, sender=typed_ws, request_obj=typed_ws)

    try:
        while True:
            try:
                message = await typed_ws.receive_json()
            except ValidationError as e:
                logger.error(f"Invalid message format: {e}")
                await typed_ws.send_error("Invalid message format")
                continue

            logger.info(f"[ws] {message.type} from {user.get('username')}")

            if isinstance(message, FetchBatches):
                await handler.fetch_batches(message.data)
                continue

            if isinstance(message, FetchBatchUploads):
                await handler.fetch_batch_uploads(message.data)
                continue

            if isinstance(message, FetchImages):
                await handler.fetch_images(message.data)
                continue

            if isinstance(message, RetryUploads):
                await handler.retry_uploads(message.data)
                continue

            if isinstance(message, SubscribeBatch):
                await handler.subscribe_batch(message.data)
                continue

            if isinstance(message, SubscribeBatchesList):
                await handler.subscribe_batches_list(message.data)
                continue

            if isinstance(message, UnsubscribeBatch):
                await handler.unsubscribe_batch()
                continue

            if isinstance(message, UnsubscribeBatchesList):
                await handler.unsubscribe_batches_list()
                continue

            if isinstance(message, Upload):
                await handler.upload(message.data)
                continue

            logger.error(
                f"[ws] Unknown action: {message.type} from {user.get('username')}"
            )
            await typed_ws.send_error("Unknown action")

    except WebSocketDisconnect:
        handler.cancel_tasks()
        return

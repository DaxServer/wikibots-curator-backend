from curator.asyncapi import (
    WS_CHANNEL_ADDRESS,
    AsyncAPIWebSocket,
    FetchBatchUploadsMessage,
    FetchBatchesMessage,
    FetchImagesMessage,
    SubscribeBatchMessage,
    UploadMessage,
)
import logging

from fastapi import APIRouter, WebSocketDisconnect, WebSocket
from pydantic import ValidationError

from curator.app.auth import LoggedInUser
from curator.app.handler import Handler

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

            if isinstance(message, FetchImagesMessage):
                await handler.fetch_images(message.data)
                continue

            if isinstance(message, UploadMessage):
                await handler.upload(message.data)
                continue

            if isinstance(message, SubscribeBatchMessage):
                await handler.subscribe_batch(message.data)
                continue

            if isinstance(message, FetchBatchesMessage):
                await handler.fetch_batches(message.data)
                continue

            if isinstance(message, FetchBatchUploadsMessage):
                await handler.fetch_batch_uploads(message.data)
                continue

            logger.error(
                f"[ws] Unknown action: {message.type} from {user.get('username')}"
            )
            await typed_ws.send_error("Unknown action")

    except WebSocketDisconnect:
        handler.cancel_tasks()
        return

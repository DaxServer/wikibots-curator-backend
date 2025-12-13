from curator.asyncapi import (
    WS_CHANNEL_ADDRESS,
    ClientMessage,
    FetchBatchUploadsMessage,
    FetchBatchesMessage,
    FetchImagesMessage,
    SubscribeBatchMessage,
    UploadMessage,
)
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter

from curator.app.auth import LoggedInUser
from curator.app.handler import Handler

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ws"])


@router.websocket(WS_CHANNEL_ADDRESS)
async def ws(websocket: WebSocket, user: LoggedInUser):
    await websocket.accept()

    logger.info(f"User {user.get('username')} connected")

    # Create the logic handler
    # websocket acts as both sender and request object (for WcqsSession)
    handler = Handler(user=user, sender=websocket, request_obj=websocket)
    adapter = TypeAdapter(ClientMessage)

    try:
        while True:
            raw_data = await websocket.receive_json()
            try:
                message = adapter.validate_python(raw_data)
            except Exception as e:
                logger.error(f"Invalid message format: {e}")
                await websocket.send_json(
                    {"type": "ERROR", "data": "Invalid message format"}
                )
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
            await websocket.send_json({"type": "ERROR", "data": "Unknown action"})

    except WebSocketDisconnect:
        handler.cancel_tasks()
        return

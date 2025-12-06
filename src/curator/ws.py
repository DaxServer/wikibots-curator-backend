import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from curator.app.auth import LoggedInUser
from curator.app.handler import Handler

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["ws"])


class WsMessage(BaseModel):
    type: str
    data: Any = None


@router.websocket("")
async def ws(websocket: WebSocket, user: LoggedInUser):
    await websocket.accept()

    logger.info(f"User {user.get('username')} connected")

    # Create the logic handler
    # websocket acts as both sender and request object (for WcqsSession)
    handler = Handler(user=user, sender=websocket, request_obj=websocket)

    try:
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
                await handler.fetch_images(data)
                continue

            if action == "UPLOAD":
                await handler.upload(data)
                continue

            if action == "SUBSCRIBE_BATCH":
                await handler.subscribe_batch(data)
                continue

            await websocket.send_json({"type": "ERROR", "data": "Unknown action"})

    except WebSocketDisconnect:
        handler.cancel_tasks()
        return

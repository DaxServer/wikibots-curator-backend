from typing import Union, List, Annotated
from fastapi import WebSocket
from pydantic import TypeAdapter, Field
from curator.asyncapi import (
    FetchImagesPayload,
    UploadPayload,
    SubscribeBatchPayload,
    FetchBatchesPayload,
    FetchBatchUploadsPayload,
    ErrorPayload,
    CollectionImagesPayload,
    UploadCreatedPayload,
    BatchesListPayload,
    BatchUploadsListPayload,
    SubscribedPayload,
    UploadsUpdatePayload,
    UploadsCompletePayload,
    BatchUploadItem,
    UploadCreatedItem,
    UploadUpdateItem,
    CollectionImagesData,
    BatchesListData,
)

WS_CHANNEL_ADDRESS: str = "/ws"

ClientMessage = Annotated[
    Union[
        FetchImagesPayload,
        UploadPayload,
        SubscribeBatchPayload,
        FetchBatchesPayload,
        FetchBatchUploadsPayload,
    ],
    Field(discriminator="type"),
]

ServerMessage = Union[
    ErrorPayload,
    CollectionImagesPayload,
    UploadCreatedPayload,
    BatchesListPayload,
    BatchUploadsListPayload,
    SubscribedPayload,
    UploadsUpdatePayload,
    UploadsCompletePayload,
]

_ClientMessageAdapter = TypeAdapter(ClientMessage)
_ServerMessageAdapter = TypeAdapter(ServerMessage)


class AsyncAPIWebSocket(WebSocket):
    async def receive_json(self, mode: str = "text") -> ClientMessage:
        data = await super().receive_json(mode=mode)
        return _ClientMessageAdapter.validate_python(data)

    async def send_json(self, data: ServerMessage, mode: str = "text") -> None:
        await super().send_json(
            _ServerMessageAdapter.dump_python(
                data, mode="json", by_alias=True, exclude_none=True
            ),
            mode=mode,
        )

    async def send_error(self, data: str) -> None:
        await self.send_json(ErrorPayload(data=data))

    async def send_collection_images(self, data: CollectionImagesData) -> None:
        await self.send_json(CollectionImagesPayload(data=data))

    async def send_upload_created(self, data: List[UploadCreatedItem]) -> None:
        await self.send_json(UploadCreatedPayload(data=data))

    async def send_batches_list(self, data: BatchesListData) -> None:
        await self.send_json(BatchesListPayload(data=data))

    async def send_batch_uploads_list(self, data: List[BatchUploadItem]) -> None:
        await self.send_json(BatchUploadsListPayload(data=data))

    async def send_subscribed(self, data: int) -> None:
        await self.send_json(SubscribedPayload(data=data))

    async def send_uploads_update(self, data: List[UploadUpdateItem]) -> None:
        await self.send_json(UploadsUpdatePayload(data=data))

    async def send_uploads_complete(self, data: int) -> None:
        await self.send_json(UploadsCompletePayload(data=data))

from datetime import datetime
from typing import Annotated, Union

from fastapi import WebSocket
from pydantic import Field, TypeAdapter

from curator.asyncapi import (
    BatchesList,
    BatchesListData,
    BatchUploadsList,
    BatchUploadsListData,
    CollectionImages,
    CollectionImagesData,
    Error,
    FetchBatches,
    FetchBatchUploads,
    FetchImages,
    RetryUploads,
    SubscribeBatch,
    SubscribeBatchesList,
    Subscribed,
    UnsubscribeBatch,
    UnsubscribeBatchesList,
    Upload,
    UploadCreated,
    UploadCreatedItem,
    UploadsComplete,
    UploadsUpdate,
    UploadUpdateItem,
)

WS_CHANNEL_ADDRESS: str = "/ws"


ClientMessage = Annotated[
    Union[
        FetchBatches,
        FetchBatchUploads,
        FetchImages,
        RetryUploads,
        SubscribeBatch,
        SubscribeBatchesList,
        UnsubscribeBatch,
        UnsubscribeBatchesList,
        Upload,
    ],
    Field(discriminator="type"),
]

ServerMessage = Annotated[
    Union[
        BatchesList,
        BatchUploadsList,
        CollectionImages,
        Error,
        Subscribed,
        UploadCreated,
        UploadsComplete,
        UploadsUpdate,
    ],
    Field(discriminator="type"),
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

    def _get_nonce(self) -> str:
        return datetime.now().isoformat()

    async def send_error(self, data: str) -> None:
        await self.send_json(Error(data=data, nonce=self._get_nonce()))

    async def send_collection_images(self, data: CollectionImagesData) -> None:
        await self.send_json(CollectionImages(data=data, nonce=self._get_nonce()))

    async def send_upload_created(self, data: list[UploadCreatedItem]) -> None:
        await self.send_json(UploadCreated(data=data, nonce=self._get_nonce()))

    async def send_batches_list(
        self, data: BatchesListData, partial: bool = False
    ) -> None:
        await self.send_json(
            BatchesList(data=data, partial=partial, nonce=self._get_nonce())
        )

    async def send_batch_uploads_list(self, data: BatchUploadsListData) -> None:
        await self.send_json(BatchUploadsList(data=data, nonce=self._get_nonce()))

    async def send_subscribed(self, data: int) -> None:
        await self.send_json(Subscribed(data=data, nonce=self._get_nonce()))

    async def send_uploads_update(self, data: list[UploadUpdateItem]) -> None:
        await self.send_json(UploadsUpdate(data=data, nonce=self._get_nonce()))

    async def send_uploads_complete(self, data: int) -> None:
        await self.send_json(UploadsComplete(data=data, nonce=self._get_nonce()))

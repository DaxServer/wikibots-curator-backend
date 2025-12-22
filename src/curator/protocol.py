from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from fastapi import WebSocket
from pydantic import Field, TypeAdapter

from curator.asyncapi import (
    BatchesList,
    BatchesListData,
    BatchUploadItem,
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
    UploadData,
    UploadItem,
    UploadsComplete,
    UploadsUpdate,
    UploadUpdateItem,
)

WS_CHANNEL_ADDRESS: str = "/ws"


class PatchedUploadItem(UploadItem):
    sdc: Optional[Union[str, List[Dict[str, Any]]]] = Field(default=None)


class PatchedUploadData(UploadData):
    items: List[PatchedUploadItem] = Field()


class PatchedUpload(Upload):
    type: Literal["UPLOAD"] = Field(default="UPLOAD", frozen=True)
    data: PatchedUploadData = Field()


class PatchedBatchUploadItem(BatchUploadItem):
    sdc: Optional[Union[str, List[Dict[str, Any]]]] = Field(default=None)


class PatchedBatchUploadsListData(BatchUploadsListData):
    uploads: List[PatchedBatchUploadItem] = Field()


class PatchedBatchUploadsList(BatchUploadsList):
    data: PatchedBatchUploadsListData = Field()


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
        PatchedUpload,
    ],
    Field(discriminator="type"),
]

ServerMessage = Union[
    BatchesList,
    PatchedBatchUploadsList,
    CollectionImages,
    Error,
    Subscribed,
    UploadCreated,
    UploadsComplete,
    UploadsUpdate,
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
        await self.send_json(Error(data=data))

    async def send_collection_images(self, data: CollectionImagesData) -> None:
        await self.send_json(CollectionImages(data=data))

    async def send_upload_created(self, data: List[UploadCreatedItem]) -> None:
        await self.send_json(UploadCreated(data=data))

    async def send_batches_list(self, data: BatchesListData) -> None:
        await self.send_json(BatchesList(data=data))

    async def send_batch_uploads_list(self, data: BatchUploadsListData) -> None:
        await self.send_json(BatchUploadsList(data=data))

    async def send_subscribed(self, data: int) -> None:
        await self.send_json(Subscribed(data=data))

    async def send_uploads_update(self, data: List[UploadUpdateItem]) -> None:
        await self.send_json(UploadsUpdate(data=data))

    async def send_uploads_complete(self, data: int) -> None:
        await self.send_json(UploadsComplete(data=data))

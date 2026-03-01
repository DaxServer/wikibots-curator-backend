from datetime import datetime
from typing import Annotated, Union

from fastapi import WebSocket
from pydantic import Field, TypeAdapter

from curator.asyncapi import (
    BatchCreated,
    BatchesList,
    BatchesListData,
    BatchUploadsList,
    BatchUploadsListData,
    CancelBatch,
    CollectionImageIds,
    CollectionImages,
    CollectionImagesData,
    CreateBatch,
    DeletePreset,
    Error,
    FetchBatches,
    FetchBatchUploads,
    FetchImages,
    FetchPresets,
    PartialCollectionImages,
    PartialCollectionImagesData,
    PresetItem,
    PresetsList,
    PresetsListData,
    RetryUploads,
    RetryUploadsResponse,
    SavePreset,
    SubscribeBatch,
    SubscribeBatchesList,
    Subscribed,
    TryBatchRetrieval,
    UnsubscribeBatch,
    UnsubscribeBatchesList,
    Upload,
    UploadCreated,
    UploadCreatedItem,
    UploadsComplete,
    UploadSlice,
    UploadSliceAck,
    UploadsUpdate,
    UploadUpdateItem,
)
from curator.asyncapi.UploadSliceAckItem import UploadSliceAckItem

WS_CHANNEL_ADDRESS: str = "/ws"


ClientMessage = Annotated[
    Union[
        CancelBatch,
        CreateBatch,
        DeletePreset,
        FetchBatches,
        FetchBatchUploads,
        FetchImages,
        FetchPresets,
        RetryUploads,
        SavePreset,
        SubscribeBatch,
        SubscribeBatchesList,
        UnsubscribeBatch,
        UnsubscribeBatchesList,
        Upload,
        UploadSlice,
    ],
    Field(discriminator="type"),
]

ServerMessage = Annotated[
    Union[
        BatchesList,
        BatchUploadsList,
        CollectionImages,
        CollectionImageIds,
        BatchCreated,
        Error,
        PartialCollectionImages,
        PresetsList,
        RetryUploadsResponse,
        Subscribed,
        TryBatchRetrieval,
        UploadCreated,
        UploadsComplete,
        UploadsUpdate,
        UploadSliceAck,
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

    async def send_try_batch_retrieval(self, data: str) -> None:
        await self.send_json(TryBatchRetrieval(data=data, nonce=self._get_nonce()))

    async def send_collection_image_ids(self, data: list[str]) -> None:
        await self.send_json(CollectionImageIds(data=data, nonce=self._get_nonce()))

    async def send_partial_collection_images(
        self, data: PartialCollectionImagesData
    ) -> None:
        await self.send_json(
            PartialCollectionImages(data=data, nonce=self._get_nonce())
        )

    async def send_batch_created(self, data: int) -> None:
        await self.send_json(BatchCreated(data=data, nonce=self._get_nonce()))

    async def send_upload_slice_ack(
        self, data: list[UploadSliceAckItem], sliceid: int
    ) -> None:
        await self.send_json(
            UploadSliceAck(data=data, sliceid=sliceid, nonce=self._get_nonce())
        )

    async def send_retry_uploads_response(self, data: int) -> None:
        await self.send_json(RetryUploadsResponse(data=data, nonce=self._get_nonce()))

    async def send_presets_list(self, handler: str, presets: list[PresetItem]) -> None:
        await self.send_json(
            PresetsList(
                data=PresetsListData(handler=handler, presets=presets),
                nonce=self._get_nonce(),
            )
        )

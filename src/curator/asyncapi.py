"""Auto-generated from asyncapi.yml. Do not edit by hand."""

from dataclasses import dataclass
from typing import Literal, Union, List, Optional, Dict, Any
from fastapi import WebSocket
from pydantic import TypeAdapter


WS_CHANNEL_ADDRESS: str = "/ws"


RECEIVE_CLIENT_MESSAGE_TYPES: List[str] = [
    "FETCH_IMAGES",
    "UPLOAD",
    "SUBSCRIBE_BATCH",
    "FETCH_BATCHES",
    "FETCH_BATCH_UPLOADS",
]
SEND_SERVER_MESSAGE_TYPES: List[str] = [
    "ERROR",
    "COLLECTION_IMAGES",
    "UPLOAD_CREATED",
    "BATCHES_LIST",
    "BATCH_UPLOADS_LIST",
    "SUBSCRIBED",
    "UPLOADS_UPDATE",
    "UPLOADS_COMPLETE",
]

ClientMessageType = Literal[
    "FETCH_IMAGES", "UPLOAD", "SUBSCRIBE_BATCH", "FETCH_BATCHES", "FETCH_BATCH_UPLOADS"
]
ServerMessageType = Literal[
    "ERROR",
    "COLLECTION_IMAGES",
    "UPLOAD_CREATED",
    "BATCHES_LIST",
    "BATCH_UPLOADS_LIST",
    "SUBSCRIBED",
    "UPLOADS_UPDATE",
    "UPLOADS_COMPLETE",
]


@dataclass
class BatchStats:
    total: int
    queued: int
    in_progress: int
    completed: int
    failed: int


@dataclass
class BatchItem:
    id: int
    created_at: str
    username: str
    userid: str
    stats: BatchStats


@dataclass
class ErrorLink:
    title: str
    url: str


@dataclass
class DuplicateError:
    type: str
    message: str
    links: List[ErrorLink]


@dataclass
class GenericError:
    type: str
    message: str


@dataclass
class BatchUploadItem:
    id: int
    status: str
    filename: str
    wikitext: str
    batchid: Optional[int] = None
    userid: Optional[str] = None
    key: Optional[str] = None
    handler: Optional[str] = None
    sdc: Optional[str] = None
    labels: Optional[Dict[str, str]] = None
    result: Optional[str] = None
    error: Optional[Union[DuplicateError, GenericError]] = None
    success: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    image_id: Optional[str] = None


@dataclass
class Creator:
    id: str
    username: str
    profile_url: str


@dataclass
class Dates:
    taken: Optional[str] = None
    published: Optional[str] = None


@dataclass
class Location:
    latitude: float
    longitude: float
    accuracy: Optional[int] = None
    compass_angle: Optional[float] = None


@dataclass
class ExistingPage:
    url: str


@dataclass
class Image:
    id: str
    title: str
    dates: Dates
    creator: Creator
    url_original: str
    thumbnail_url: str
    preview_url: str
    url: str
    width: int
    height: int
    description: Optional[str] = None
    location: Optional[Location] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    is_pano: Optional[bool] = None
    license: Optional[str] = None
    tags: Optional[List[str]] = None
    existing: Optional[List[ExistingPage]] = None


@dataclass
class UploadCreatedItem:
    id: int
    status: str
    image_id: str
    input: str
    batch_id: int


@dataclass
class UploadItem:
    id: str
    input: str
    title: str
    wikitext: str
    labels: Optional[Dict[str, str]] = None
    sdc: Optional[List[Dict[str, Any]]] = None


@dataclass
class UploadUpdateItem:
    id: int
    status: str
    key: str
    handler: str
    error: Optional[Union[DuplicateError, GenericError]] = None
    success: Optional[str] = None


@dataclass
class FetchImagesMessage:
    type: Literal["FETCH_IMAGES"]
    data: "str"


@dataclass
class UploadMessage:
    type: Literal["UPLOAD"]
    data: "UploadData"


@dataclass
class SubscribeBatchMessage:
    type: Literal["SUBSCRIBE_BATCH"]
    data: "int"


@dataclass
class FetchBatchesMessage:
    type: Literal["FETCH_BATCHES"]
    data: "FetchBatchesData"


@dataclass
class FetchBatchUploadsMessage:
    type: Literal["FETCH_BATCH_UPLOADS"]
    data: "FetchBatchUploadsData"


@dataclass
class ErrorMessage:
    type: Literal["ERROR"]
    data: "str"


@dataclass
class CollectionImagesMessage:
    type: Literal["COLLECTION_IMAGES"]
    data: "CollectionImagesData"


@dataclass
class UploadCreatedMessage:
    type: Literal["UPLOAD_CREATED"]
    data: "List[UploadCreatedItem]"


@dataclass
class BatchesListMessage:
    type: Literal["BATCHES_LIST"]
    data: "BatchesListData"


@dataclass
class BatchUploadsListMessage:
    type: Literal["BATCH_UPLOADS_LIST"]
    data: "List[BatchUploadItem]"


@dataclass
class SubscribedMessage:
    type: Literal["SUBSCRIBED"]
    data: "int"


@dataclass
class UploadsUpdateMessage:
    type: Literal["UPLOADS_UPDATE"]
    data: "List[UploadUpdateItem]"


@dataclass
class UploadsCompleteMessage:
    type: Literal["UPLOADS_COMPLETE"]
    data: "int"


@dataclass
class UploadData:
    items: List[UploadItem]
    handler: Optional[str] = None


@dataclass
class FetchBatchesData:
    page: Optional[int] = None
    limit: Optional[int] = None
    userid: Optional[str] = None


@dataclass
class FetchBatchUploadsData:
    batch_id: int


@dataclass
class CollectionImagesData:
    images: Dict[str, Image]
    creator: Creator


@dataclass
class BatchesListData:
    items: List[BatchItem]
    total: int


ClientMessage = Union[
    FetchImagesMessage,
    UploadMessage,
    SubscribeBatchMessage,
    FetchBatchesMessage,
    FetchBatchUploadsMessage,
]

ServerMessage = Union[
    ErrorMessage,
    CollectionImagesMessage,
    UploadCreatedMessage,
    BatchesListMessage,
    BatchUploadsListMessage,
    SubscribedMessage,
    UploadsUpdateMessage,
    UploadsCompleteMessage,
]

_ClientMessageAdapter = TypeAdapter(ClientMessage)
_ServerMessageAdapter = TypeAdapter(ServerMessage)


class AsyncAPIWebSocket(WebSocket):
    async def receive_json(self, mode: str = "text") -> ClientMessage:
        data = await super().receive_json(mode=mode)
        return _ClientMessageAdapter.validate_python(data)

    async def send_json(self, data: ServerMessage, mode: str = "text") -> None:
        await super().send_json(
            _ServerMessageAdapter.dump_python(data, mode="json"), mode=mode
        )

    async def send_error(self, data: str) -> None:
        await self.send_json(ErrorMessage(type="ERROR", data=data))

    async def send_collection_images(self, data: CollectionImagesData) -> None:
        await self.send_json(
            CollectionImagesMessage(type="COLLECTION_IMAGES", data=data)
        )

    async def send_upload_created(self, data: List[UploadCreatedItem]) -> None:
        await self.send_json(UploadCreatedMessage(type="UPLOAD_CREATED", data=data))

    async def send_batches_list(self, data: BatchesListData) -> None:
        await self.send_json(BatchesListMessage(type="BATCHES_LIST", data=data))

    async def send_batch_uploads_list(self, data: List[BatchUploadItem]) -> None:
        await self.send_json(
            BatchUploadsListMessage(type="BATCH_UPLOADS_LIST", data=data)
        )

    async def send_subscribed(self, data: int) -> None:
        await self.send_json(SubscribedMessage(type="SUBSCRIBED", data=data))

    async def send_uploads_update(self, data: List[UploadUpdateItem]) -> None:
        await self.send_json(UploadsUpdateMessage(type="UPLOADS_UPDATE", data=data))

    async def send_uploads_complete(self, data: int) -> None:
        await self.send_json(UploadsCompleteMessage(type="UPLOADS_COMPLETE", data=data))

from typing import Literal, Union, List, Optional, Dict
from pydantic import BaseModel
from curator.app.models import UploadItem, StructuredError
from curator.app.image_models import Image, Creator


class FetchImagesMessage(BaseModel):
    type: Literal["FETCH_IMAGES"]
    data: str


class UploadData(BaseModel):
    items: List[UploadItem]
    handler: Optional[str] = None


class UploadMessage(BaseModel):
    type: Literal["UPLOAD"]
    data: UploadData


class SubscribeBatchMessage(BaseModel):
    type: Literal["SUBSCRIBE_BATCH"]
    data: int


class FetchBatchesPayload(BaseModel):
    page: int = 1
    limit: int = 100
    userid: Optional[str] = None


class FetchBatchesMessage(BaseModel):
    type: Literal["FETCH_BATCHES"]
    data: FetchBatchesPayload


class FetchBatchUploadsPayload(BaseModel):
    batch_id: int


class FetchBatchUploadsMessage(BaseModel):
    type: Literal["FETCH_BATCH_UPLOADS"]
    data: FetchBatchUploadsPayload


ClientMessage = Union[
    FetchImagesMessage,
    UploadMessage,
    SubscribeBatchMessage,
    FetchBatchesMessage,
    FetchBatchUploadsMessage,
]


class ErrorMessage(BaseModel):
    type: Literal["ERROR"]
    data: str


class CollectionImagesData(BaseModel):
    images: Dict[str, Image]
    creator: Creator


class CollectionImagesMessage(BaseModel):
    type: Literal["COLLECTION_IMAGES"]
    data: CollectionImagesData


class UploadCreatedItem(BaseModel):
    id: int
    status: str
    image_id: str
    input: str
    batch_id: int


class UploadCreatedMessage(BaseModel):
    type: Literal["UPLOAD_CREATED"]
    data: List[UploadCreatedItem]


class BatchStats(BaseModel):
    total: int
    queued: int
    in_progress: int
    completed: int
    failed: int


class BatchItem(BaseModel):
    id: int
    created_at: str
    username: str
    userid: str
    stats: BatchStats


class BatchesListData(BaseModel):
    items: List[BatchItem]
    total: int


class BatchesListMessage(BaseModel):
    type: Literal["BATCHES_LIST"]
    data: BatchesListData


class BatchUploadItem(BaseModel):
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
    error: Optional[StructuredError] = None
    success: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    image_id: Optional[str] = None


class BatchUploadsListMessage(BaseModel):
    type: Literal["BATCH_UPLOADS_LIST"]
    data: List[BatchUploadItem]


class SubscribedMessage(BaseModel):
    type: Literal["SUBSCRIBED"]
    data: int


class UploadUpdateItem(BaseModel):
    id: int
    status: str
    key: str
    error: Optional[StructuredError] = None
    success: Optional[str] = None
    handler: str


class UploadsUpdateMessage(BaseModel):
    type: Literal["UPLOADS_UPDATE"]
    data: List[UploadUpdateItem]


class UploadsCompleteMessage(BaseModel):
    type: Literal["UPLOADS_COMPLETE"]
    data: int


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

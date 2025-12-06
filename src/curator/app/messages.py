from typing import Literal, Union, List, Optional
from pydantic import BaseModel
from curator.app.models import UploadItem


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
    page: int = 1
    limit: int = 100
    columns: Optional[str] = None


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

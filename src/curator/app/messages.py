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


ClientMessage = Union[FetchImagesMessage, UploadMessage, SubscribeBatchMessage]

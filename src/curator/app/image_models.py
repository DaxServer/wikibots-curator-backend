from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class Creator(BaseModel):
    id: str
    username: str
    profile_url: str


class Location(BaseModel):
    latitude: float
    longitude: float
    accuracy: Optional[int] = None
    compass_angle: Optional[float] = None


class Dates(BaseModel):
    taken: Optional[datetime] = None
    published: Optional[datetime] = None


class Image(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    dates: Dates
    creator: Creator
    location: Optional[Location] = None
    url_original: str
    thumbnail_url: str
    preview_url: str
    url: str
    width: int
    height: int
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    is_pano: Optional[bool] = None
    license: Optional[str] = None
    tags: list[str] = []

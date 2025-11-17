from typing import Optional, Dict, Any
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


class Image(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    captured_at: str
    creator: Creator
    location: Optional[Location] = None
    url_original: str
    thumbnail_url: str
    preview_url: str
    width: int
    height: int
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    compass_angle: Optional[float] = None
    is_pano: Optional[bool] = None
    license: Optional[str] = None
    tags: Optional[list[str]] = None


def from_mapillary(image: Dict[str, Any]) -> Image:
    coords = image.get("geometry").get("coordinates")
    owner = image.get("creator")
    creator = Creator(
        id=str(owner.get("id")),
        username=owner.get("username"),
        profile_url=f"https://www.mapillary.com/app/user/{owner.get('username')}",
    )
    loc = Location(latitude=coords[1], longitude=coords[0])
    dt = datetime.fromtimestamp(image.get("captured_at") / 1000.0)
    captured_at = dt.isoformat().replace("+00:00", "Z")
    date = captured_at.split("T")[0]
    return Image(
        id=str(image.get("id")),
        title=f"Photo from Mapillary {date} ({str(image.get('id'))}).jpg",
        captured_at=captured_at,
        creator=creator,
        location=loc,
        url_original=image.get("thumb_original_url"),
        thumbnail_url=image.get("thumb_256_url"),
        preview_url=image.get("thumb_1024_url"),
        width=image.get("width"),
        height=image.get("height"),
        camera_make=image.get("make"),
        camera_model=image.get("model"),
        compass_angle=image.get("compass_angle"),
        is_pano=image.get("is_pano"),
    )

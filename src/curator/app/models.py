import uuid
from typing import Optional
from sqlmodel import Field, SQLModel, Relationship
from datetime import datetime


class User(SQLModel, table=True):
    __tablename__ = "users"

    userid: str = Field(primary_key=True, max_length=255)
    username: str = Field(index=True, max_length=255)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(
        default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now}
    )

    batches: list["Batch"] = Relationship(back_populates="user")
    uploads: list["UploadRequest"] = Relationship(back_populates="user")


class Batch(SQLModel, table=True):
    __tablename__ = "batches"

    batch_uid: str = Field(primary_key=True, max_length=255, default_factory=lambda: str(uuid.uuid4()))
    userid: str = Field(foreign_key="users.userid", index=True, max_length=255)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(
        default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now}
    )

    user: Optional[User] = Relationship(back_populates="batches")


class UploadRequest(SQLModel, table=True):
    __tablename__ = "upload_requests"

    id: int = Field(default=None, primary_key=True)
    batch_id: str = Field(foreign_key="batches.batch_uid", index=True, max_length=255)
    userid: str = Field(foreign_key="users.userid", index=True, max_length=255)
    status: str = Field(index=True, max_length=50)
    key: str = Field(index=True, max_length=255)
    handler: str = Field(index=True, max_length=255)
    filename: str = Field(index=True, max_length=255)
    wikitext: Optional[str] = Field(default=None, max_length=2000)
    sdc: Optional[str] = Field(default=None, max_length=2000)
    result: Optional[str] = Field(default=None, max_length=2000)
    error: Optional[str] = Field(default=None, max_length=2000)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(
        default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now}
    )

    user: Optional[User] = Relationship(back_populates="uploads")


class UploadItem(SQLModel):
    id: str
    sequence_id: str
    title: str
    wikitext: str

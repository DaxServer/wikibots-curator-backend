from datetime import datetime
from typing import Literal, Optional, TypedDict, Union

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, Relationship, SQLModel


class ErrorLink(TypedDict):
    title: str
    url: str


class DuplicateError(TypedDict):
    type: Literal["duplicate"]
    message: str
    links: list[ErrorLink]


class GenericError(TypedDict):
    type: Literal["error"]
    message: str


StructuredError = Union[DuplicateError, GenericError]


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

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
    __table_args__ = {"extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    userid: str = Field(foreign_key="users.userid", index=True, max_length=255)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(
        default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now}
    )

    user: Optional[User] = Relationship(back_populates="batches")
    uploads: list["UploadRequest"] = Relationship(back_populates="batch")


class UploadRequest(SQLModel, table=True):
    __tablename__ = "upload_requests"
    __table_args__ = {"extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    batchid: int = Field(default=None, foreign_key="batches.id")
    userid: str = Field(foreign_key="users.userid", index=True, max_length=255)
    status: str = Field(index=True, max_length=50)
    key: str = Field(index=True, max_length=255)
    handler: str = Field(index=True, max_length=255)
    collection: Optional[str] = Field(default=None, max_length=255)
    access_token: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        exclude=True,
    )
    filename: str = Field(index=True, max_length=255)
    wikitext: Optional[str] = Field(default=None, sa_column=Column(Text))
    sdc: Optional[str] = Field(default=None, sa_column=Column(Text))
    labels: Optional[dict[str, str]] = Field(default=None, sa_column=Column(JSON))
    result: Optional[str] = Field(default=None, sa_column=Column(Text))
    error: Optional[StructuredError] = Field(default=None, sa_column=Column(JSON))
    success: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(
        default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now}
    )

    user: Optional[User] = Relationship(back_populates="uploads")
    batch: Optional[Batch] = Relationship(back_populates="uploads")


class UploadItem(SQLModel):
    id: str
    input: str
    title: str
    wikitext: str
    labels: Optional[dict[str, str]] = None
    sdc: Optional[list[dict]] = None

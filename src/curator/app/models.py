from datetime import datetime
from typing import Optional, Union

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, Relationship, SQLModel

from curator.asyncapi import (
    DuplicateError,
    GenericError,
    Label,
    Statement,
    TitleBlacklistedError,
)

StructuredError = Union[DuplicateError, GenericError, TitleBlacklistedError]


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
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(
        default_factory=datetime.now,
        index=True,
        sa_column_kwargs={"onupdate": datetime.now},
    )

    user: Optional[User] = Relationship(back_populates="batches")
    uploads: list["UploadRequest"] = Relationship(back_populates="batch")


class UploadRequest(SQLModel, table=True):
    __tablename__ = "upload_requests"
    __table_args__ = {"extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    batchid: int = Field(foreign_key="batches.id", index=True)
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
    wikitext: str = Field(sa_column=Column(Text))
    copyright_override: bool = Field(default=False)
    sdc: Optional[list[Statement]] = Field(default=[], sa_column=Column(JSON))
    labels: Optional[Label] = Field(default=None, sa_column=Column(JSON))
    result: Optional[str] = Field(default=None, sa_column=Column(Text))
    error: Optional[StructuredError] = Field(default=None, sa_column=Column(JSON))
    success: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(
        default_factory=datetime.now,
        index=True,
        sa_column_kwargs={"onupdate": datetime.now},
    )

    user: Optional[User] = Relationship(back_populates="uploads")
    batch: Optional[Batch] = Relationship(back_populates="uploads")


class UploadItem(SQLModel):
    id: str
    input: str
    title: str
    wikitext: str
    labels: Optional[Label] = None
    copyright_override: bool = False
    sdc: Optional[list[Statement]] = []

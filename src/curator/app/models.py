from datetime import datetime
from typing import Optional, Union

from pydantic import BaseModel, TypeAdapter
from sqlalchemy import JSON, Column, Text
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, Relationship, SQLModel

from curator.asyncapi import (
    DuplicatedSdcNotUpdatedError,
    DuplicatedSdcUpdatedError,
    DuplicateError,
    GenericError,
    Label,
    TitleBlacklistedError,
)

StructuredError = Union[
    DuplicateError,
    DuplicatedSdcNotUpdatedError,
    DuplicatedSdcUpdatedError,
    GenericError,
    TitleBlacklistedError,
]

_error_adapter: TypeAdapter[StructuredError] = TypeAdapter(StructuredError)


class LabelJSON(TypeDecorator[Optional[Label]]):
    """JSON column that serializes Label to dict and deserializes dict to Label."""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: object, dialect: object) -> object:
        """Convert Label to dict for storage."""
        if isinstance(value, Label):
            return value.model_dump()
        return value

    def process_result_value(self, value: object, dialect: object) -> Optional[Label]:
        """Convert dict from storage to Label."""
        if value is None:
            return None
        if isinstance(value, dict):
            return Label.model_validate(value)
        return None


class StructuredErrorJSON(TypeDecorator[Optional[StructuredError]]):
    """JSON column that serializes StructuredError to dict and deserializes to typed error."""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: object, dialect: object) -> object:
        """Convert StructuredError to dict for storage."""
        if isinstance(value, BaseModel):
            return value.model_dump()
        return value

    def process_result_value(
        self, value: object, dialect: object
    ) -> Optional[StructuredError]:
        """Convert dict from storage to typed error instance."""
        if value is None:
            return None
        if isinstance(value, dict):
            return _error_adapter.validate_python(value)
        return None


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
    uploads: list["UploadRequest"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={
            "primaryjoin": "User.userid==UploadRequest.userid",
        },
    )
    presets: list["Preset"] = Relationship(back_populates="user")


class Preset(SQLModel, table=True):
    __tablename__ = "presets"
    __table_args__ = {"extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    userid: str = Field(foreign_key="users.userid", index=True, max_length=255)
    handler: str = Field(index=True, max_length=50)
    title: str = Field(max_length=255)
    title_template: str = Field(max_length=500)
    labels: Optional[Label] = Field(default=None, sa_column=Column(LabelJSON))
    categories: Optional[str] = Field(default=None, max_length=500)
    exclude_from_date_category: bool = Field(default=False)
    is_default: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(
        default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now}
    )

    user: Optional[User] = Relationship(back_populates="presets")


class Batch(SQLModel, table=True):
    __tablename__ = "batches"
    __table_args__ = {"extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    userid: str = Field(foreign_key="users.userid", index=True, max_length=255)
    edit_group_id: str | None = Field(default=None, max_length=12)
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
    labels: Optional[Label] = Field(default=None, sa_column=Column(LabelJSON))
    result: Optional[str] = Field(default=None, sa_column=Column(Text))
    error: Optional[StructuredError] = Field(
        default=None, sa_column=Column(StructuredErrorJSON)
    )
    success: Optional[str] = Field(default=None, sa_column=Column(Text))
    last_edited_by: Optional[str] = Field(
        default=None, foreign_key="users.userid", index=True, max_length=255
    )
    celery_task_id: Optional[str] = Field(default=None, max_length=255)
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(
        default_factory=datetime.now,
        index=True,
        sa_column_kwargs={"onupdate": datetime.now},
    )

    user: Optional[User] = Relationship(
        back_populates="uploads",
        sa_relationship_kwargs={
            "primaryjoin": "User.userid==UploadRequest.userid",
        },
    )
    last_editor: Optional[User] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "UploadRequest.last_edited_by==User.userid",
            "foreign_keys": "UploadRequest.last_edited_by",
        }
    )
    batch: Optional[Batch] = Relationship(back_populates="uploads")


class UploadItem(SQLModel):
    id: str
    input: str
    title: str
    wikitext: str
    labels: Optional[Label] = None
    copyright_override: bool = False


class RetrySelectedUploadsRequest(SQLModel):
    upload_ids: list[int]

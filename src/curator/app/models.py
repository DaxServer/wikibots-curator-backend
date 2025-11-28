from typing import Optional
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, JSON, Text
from datetime import datetime


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
    filename: str = Field(index=True, max_length=255)
    wikitext: Optional[str] = Field(default=None, sa_column=Column(Text))
    sdc: Optional[str] = Field(default=None, sa_column=Column(Text))
    labels: Optional[dict[str, str]] = Field(default=None, sa_column=Column(JSON))
    result: Optional[str] = Field(default=None, sa_column=Column(Text))
    error: Optional[str] = Field(default=None, sa_column=Column(Text))
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

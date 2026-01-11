from abc import ABC, abstractmethod
from typing import Optional, Union

from fastapi import Request, WebSocket

from curator.asyncapi import ExistingPage, MediaImage


class Handler(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def fetch_collection(self, input: str) -> dict[str, MediaImage]: ...

    @abstractmethod
    async def fetch_image_metadata(
        self, image_id: str, input: Optional[str] = None
    ) -> MediaImage: ...

    @abstractmethod
    def fetch_existing_pages(
        self, image_ids: list[str], request: Union[Request, WebSocket]
    ) -> dict[str, list[ExistingPage]]: ...

    @abstractmethod
    async def fetch_collection_ids(self, input: str) -> list[str]: ...

    @abstractmethod
    async def fetch_images_batch(
        self, image_ids: list[str], input: str
    ) -> dict[str, MediaImage]: ...

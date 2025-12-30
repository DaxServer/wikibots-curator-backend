from typing import Optional, Protocol, Union

from fastapi import Request, WebSocket

from curator.asyncapi import ExistingPage, MediaImage


class Handler(Protocol):
    name: str

    async def fetch_collection(self, input: str) -> dict[str, MediaImage]: ...

    async def fetch_image_metadata(
        self, image_id: str, input: Optional[str] = None
    ) -> MediaImage: ...

    def fetch_existing_pages(
        self, image_ids: list[str], request: Union[Request, WebSocket]
    ) -> dict[str, list[ExistingPage]]: ...

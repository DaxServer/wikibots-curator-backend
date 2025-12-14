from typing import Dict, List, Protocol

from fastapi import Request

from curator.app.image_models import ExistingPage, Image


class Handler(Protocol):
    name: str

    async def fetch_collection(self, input: str) -> Dict[str, Image]: ...

    async def fetch_image_metadata(self, image_id: str, input: str) -> Image: ...

    def fetch_existing_pages(
        self, image_ids: List[str], request: Request
    ) -> Dict[str, List[ExistingPage]]: ...

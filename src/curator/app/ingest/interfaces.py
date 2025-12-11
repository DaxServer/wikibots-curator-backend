from curator.app.image_models import Image, ExistingPage
from typing import Protocol, Dict, List
from fastapi import Request


class Handler(Protocol):
    name: str

    async def fetch_collection(self, input: str) -> Dict[str, Image]: ...

    async def fetch_image_metadata(self, image_id: str, input: str) -> Image: ...

    def build_sdc(self, image: Image) -> List[Dict]: ...

    def fetch_existing_pages(
        self, image_ids: List[str], request: Request
    ) -> Dict[str, List[ExistingPage]]: ...

from curator.app.image_models import Image
from typing import Protocol, Dict, List


class Handler(Protocol):
    name: str

    def fetch_collection(self, input: str) -> Dict[str, Image]: ...

    def fetch_image_metadata(self, image_id: str, input: str) -> Image: ...

    def build_sdc(self, image: Image) -> List[Dict]: ...

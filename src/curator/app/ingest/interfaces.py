from typing import Protocol, Dict, List


class Handler(Protocol):
    name: str

    def fetch_collection(self, input: str) -> Dict[str, Dict]: ...

    def fetch_image_metadata(self, image_id: str, input: str) -> Dict: ...

    def build_sdc(self, image: Dict) -> List[Dict]: ...

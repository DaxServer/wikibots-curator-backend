import copy
import threading
from typing import Any, MutableMapping


class ThreadLocalDict(MutableMapping):
    """
    A dictionary that stores its contents in thread-local storage.
    Used to patch global configuration objects to be thread-safe.
    """

    def __init__(self, initial_data: dict | None = None):
        self._local = threading.local()
        self._initial_data = initial_data or {}

    @property
    def _store(self) -> dict:
        if not hasattr(self._local, "store"):
            # Initialize with a deep copy of initial data for complete isolation
            self._local.store = copy.deepcopy(self._initial_data)
        return self._local.store

    def __getitem__(self, key: Any) -> Any:
        return self._store[key]

    def __setitem__(self, key: Any, value: Any) -> None:
        self._store[key] = value

    def __delitem__(self, key: Any) -> None:
        del self._store[key]

    def __iter__(self):
        return iter(self._store)

    def __len__(self) -> int:
        return len(self._store)

    def __repr__(self) -> str:
        return f"ThreadLocalDict({self._store})"

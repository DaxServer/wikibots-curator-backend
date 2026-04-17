"""Error classes for curator application."""

from curator.asyncapi import ErrorLink


class DuplicateUploadError(Exception):
    def __init__(self, duplicates: list[ErrorLink], message: str):
        super().__init__(message)
        self.duplicates = duplicates


class HashLockError(Exception):
    """Raised when file hash is locked by another worker"""

    pass


class StorageError(Exception):
    """Raised when the MediaWiki storage backend fails persistently"""

    pass


class SourceCdnError(Exception):
    """Raised when the image source CDN fails with a 5xx error after all download retries"""

    pass

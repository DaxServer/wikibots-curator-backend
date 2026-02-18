"""Error classes for curator application."""

from curator.asyncapi import ErrorLink


class DuplicateUploadError(Exception):
    def __init__(self, duplicates: list[ErrorLink], message: str):
        super().__init__(message)
        self.duplicates = duplicates

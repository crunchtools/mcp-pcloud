"""Pydantic input models for pCloud tools.

Every tool validates its arguments through one of these models. All models
forbid extra fields so unexpected keys are rejected rather than forwarded
to the pCloud API.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_PATH_LENGTH = 4096
MAX_QUERY_LENGTH = 256
MAX_NAME_LENGTH = 255

_TRAVERSAL = re.compile(r"(^|/)\.\.(/|$)")


def _validate_path(value: str) -> str:
    """Normalize a pCloud path and reject unsafe forms.

    Paths must be absolute and free of NUL bytes. Traversal segments are
    rejected so a caller cannot escape a folder they were scoped to by a
    gateway tool allowlist upstream. A trailing slash is collapsed so
    '/Docs/' and '/Docs' address the same target.
    """
    path = value.strip()
    if not path:
        raise ValueError("path must not be empty")
    if not path.startswith("/"):
        raise ValueError("path must be absolute and start with '/'")
    if "\x00" in path:
        raise ValueError("path must not contain null bytes")
    if _TRAVERSAL.search(path):
        raise ValueError("path must not contain '..' traversal segments")
    if len(path) > MAX_PATH_LENGTH:
        raise ValueError(f"path must be at most {MAX_PATH_LENGTH} characters")
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path


class _Base(BaseModel):
    """Base model rejecting unknown fields."""

    model_config = ConfigDict(extra="forbid")


class PathInput(_Base):
    """A single absolute pCloud path."""

    path: str = Field(description="Absolute pCloud path, e.g. /Documents/file.txt")

    @field_validator("path")
    @classmethod
    def check_path(cls, value: str) -> str:
        """Validate the path argument."""
        return _validate_path(value)


class ListFolderInput(_Base):
    """Arguments for listing a folder."""

    path: str = Field(default="/", description="Absolute folder path (default: /)")
    recursive: bool = Field(
        default=False, description="Whether to list contents recursively"
    )

    @field_validator("path")
    @classmethod
    def check_path(cls, value: str) -> str:
        """Validate the folder path."""
        return _validate_path(value)


class DeleteFolderInput(_Base):
    """Arguments for deleting a folder."""

    path: str = Field(description="Absolute folder path to delete")
    recursive: bool = Field(
        default=False,
        description="Delete folder contents too. Without this a non-empty "
        "folder is refused by pCloud.",
    )

    @field_validator("path")
    @classmethod
    def check_path(cls, value: str) -> str:
        """Validate the folder path."""
        return _validate_path(value)


class MoveInput(_Base):
    """Arguments for a rename or copy between two paths."""

    path: str = Field(description="Absolute source path")
    to_path: str = Field(description="Absolute destination path")

    @field_validator("path", "to_path")
    @classmethod
    def check_paths(cls, value: str) -> str:
        """Validate both source and destination paths."""
        return _validate_path(value)


class SearchInput(_Base):
    """Arguments for searching pCloud."""

    query: str = Field(description="Search text matched against file names")
    path: str = Field(default="/", description="Folder to search within")

    @field_validator("query")
    @classmethod
    def check_query(cls, value: str) -> str:
        """Validate the search query."""
        query = value.strip()
        if not query:
            raise ValueError("query must not be empty")
        if len(query) > MAX_QUERY_LENGTH:
            raise ValueError(f"query must be at most {MAX_QUERY_LENGTH} characters")
        return query

    @field_validator("path")
    @classmethod
    def check_path(cls, value: str) -> str:
        """Validate the search root path."""
        return _validate_path(value)

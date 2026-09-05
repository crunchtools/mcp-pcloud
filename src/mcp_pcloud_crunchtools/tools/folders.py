"""Folder operations against the pCloud API."""

from __future__ import annotations

from typing import Any

from ..client import get_client
from .formatting import format_listing


async def list_folder(path: str, recursive: bool) -> str:
    """List the contents of a pCloud folder."""
    params: dict[str, Any] = {"path": path}
    if recursive:
        params["recursive"] = 1
    payload = await get_client().call("listfolder", params, context=path)
    contents = payload.get("metadata", {}).get("contents", [])
    return format_listing(contents, f"Contents of {path}:")


async def create_folder(path: str) -> str:
    """Create a folder, succeeding if it already exists."""
    payload = await get_client().call(
        "createfolderifnotexists", {"path": path}, context=path
    )
    created = payload.get("created", True)
    verb = "Created" if created else "Already present"
    return f"{verb}: {path}"


async def delete_folder(path: str, recursive: bool) -> str:
    """Delete a folder, optionally including its contents."""
    method = "deletefolderrecursive" if recursive else "deletefolder"
    await get_client().call(method, {"path": path}, context=path)
    suffix = " and its contents" if recursive else ""
    return f"Deleted folder{suffix}: {path}"


async def rename_folder(path: str, to_path: str) -> str:
    """Rename or move a folder."""
    await get_client().call(
        "renamefolder", {"path": path, "topath": to_path}, context=path
    )
    return f"Renamed folder {path} -> {to_path}"


async def copy_folder(path: str, to_path: str) -> str:
    """Copy a folder to a new location."""
    await get_client().call(
        "copyfolder", {"path": path, "topath": to_path}, context=path
    )
    return f"Copied folder {path} -> {to_path}"

"""File operations against the pCloud API."""

from __future__ import annotations

from ..client import get_client
from ..errors import PCloudApiError
from .formatting import format_entry


async def get_file_info(path: str) -> str:
    """Return metadata for a single file."""
    payload = await get_client().call("stat", {"path": path}, context=path)
    return format_entry(payload.get("metadata", {}))


async def delete_file(path: str) -> str:
    """Delete a file."""
    await get_client().call("deletefile", {"path": path}, context=path)
    return f"Deleted file: {path}"


async def rename_file(path: str, to_path: str) -> str:
    """Rename or move a file."""
    await get_client().call(
        "renamefile", {"path": path, "topath": to_path}, context=path
    )
    return f"Renamed file {path} -> {to_path}"


async def copy_file(path: str, to_path: str) -> str:
    """Copy a file to a new location."""
    await get_client().call(
        "copyfile", {"path": path, "topath": to_path}, context=path
    )
    return f"Copied file {path} -> {to_path}"


async def read_text_file(path: str) -> str:
    """Read a UTF-8 text file's contents."""
    client = get_client()
    payload = await client.call("gettextfile", {"path": path}, context=path)

    hosts = payload.get("hosts") or []
    content_path = payload.get("path")
    if not hosts or not content_path:
        raise PCloudApiError(0, "pCloud returned no download host for the file")

    return await client.fetch_text(f"https://{hosts[0]}{content_path}")


async def get_checksum(path: str) -> str:
    """Return pCloud's stored checksums for a file."""
    payload = await get_client().call("checksumfile", {"path": path}, context=path)
    parts = [
        f"{algorithm.upper()}: {payload[algorithm]}"
        for algorithm in ("sha256", "sha1", "md5")
        if payload.get(algorithm)
    ]
    if not parts:
        return f"No checksums available for {path}"
    joined = "\n  ".join(parts)
    return f"Checksums for {path}:\n  {joined}"

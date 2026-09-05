"""Search operations against the pCloud API."""

from __future__ import annotations

from ..client import get_client
from .formatting import format_listing


async def search(query: str, path: str) -> str:
    """Search for files and folders by name."""
    payload = await get_client().call(
        "search", {"query": query, "path": path}, context=path
    )
    matches = payload.get("metadata", [])
    return format_listing(matches, f"Search results for '{query}' under {path}:")

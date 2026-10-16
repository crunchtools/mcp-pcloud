"""Search operations against the pCloud API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..client import get_client
from .formatting import format_listing

MAX_DEPTH = 8
MAX_RESULTS = 100


@dataclass
class _Walk:
    """Search state: the needle, collected matches, and whether the depth bound hid folders."""

    needle: str
    matches: list[dict[str, Any]] = field(default_factory=list)
    too_deep: bool = False

    def run(self, contents: list[dict[str, Any]], parent: str, depth: int) -> bool:
        """Collect name matches; return True if the result cap cut the walk short."""
        for item in contents:
            name = str(item.get("name", ""))
            path = f"{parent.rstrip('/')}/{name}"
            if self.needle in name.lower():
                if len(self.matches) >= MAX_RESULTS:
                    return True
                self.matches.append({**item, "path": item.get("path", path)})
            children: list[dict[str, Any]] = item.get("contents") or []
            if not (item.get("isfolder") and children):
                continue
            if depth >= MAX_DEPTH:
                self.too_deep = True
            elif self.run(children, path, depth + 1):
                return True
        return False


async def search(query: str, path: str) -> str:
    """Search for files and folders by name under a folder.

    pCloud has no usable name-search method, so this lists ``path`` recursively
    and matches names case-insensitively by substring, bounded by depth and
    result count.
    """
    payload = await get_client().call("listfolder", {"path": path, "recursive": 1}, context=path)
    contents = payload.get("metadata", {}).get("contents", [])
    walk = _Walk(query.lower())
    truncated = walk.run(contents, path, 1)
    header = f"Search results for '{query}' under {path}:"
    out = format_listing(walk.matches, header)
    if truncated:
        out += f"\n\n(truncated at {MAX_RESULTS} results; narrow the query or path)"
    if walk.too_deep:
        out += f"\n\n(folders deeper than {MAX_DEPTH} levels were not searched)"
    return out

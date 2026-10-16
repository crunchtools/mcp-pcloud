"""Search operations against the pCloud API."""

from __future__ import annotations

from typing import Any

from ..client import get_client
from .formatting import format_listing

MAX_DEPTH = 8
MAX_RESULTS = 100


def _walk(
    contents: list[dict[str, Any]],
    parent: str,
    needle: str,
    depth: int,
    matches: list[dict[str, Any]],
    too_deep: list[str],
) -> bool:
    """Collect name matches into ``matches``; return True if the cap cut the walk short.

    Folders with contents that sit past MAX_DEPTH are recorded in ``too_deep``.
    """
    for item in contents:
        name = str(item.get("name", ""))
        path = f"{parent.rstrip('/')}/{name}"
        if needle in name.lower():
            if len(matches) >= MAX_RESULTS:
                return True
            matches.append({**item, "path": item.get("path", path)})
        children: list[dict[str, Any]] = item.get("contents") or []
        if not (item.get("isfolder") and children):
            continue
        if depth >= MAX_DEPTH:
            too_deep.append(path)
        elif _walk(children, path, needle, depth + 1, matches, too_deep):
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
    matches: list[dict[str, Any]] = []
    too_deep: list[str] = []
    truncated = _walk(contents, path, query.lower(), 1, matches, too_deep)
    header = f"Search results for '{query}' under {path}:"
    out = format_listing(matches, header)
    if truncated:
        out += f"\n\n(truncated at {MAX_RESULTS} results; narrow the query or path)"
    elif too_deep:
        out += f"\n\n(folders deeper than {MAX_DEPTH} levels were not searched)"
    return out

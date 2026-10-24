"""Search operations against the pCloud API."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ..client import get_client
from .formatting import format_listing

MAX_DEPTH = 8
MAX_RESULTS = 100
MAX_LISTINGS = 200
LISTING_BATCH = 8


@dataclass
class _Walk:
    """Search state: the needle, collected matches, and which bound stopped the walk."""

    needle: str
    matches: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False
    too_deep: bool = False
    out_of_listings: bool = False

    async def run(self, root: str) -> None:
        """List folders breadth-first from ``root``, a few listfolder calls at a time."""
        client = get_client()
        pending: deque[tuple[str, int]] = deque([(root, 1)])
        listings = 0
        while pending and not self.truncated:
            if listings >= MAX_LISTINGS:
                self.out_of_listings = True
                return
            size = min(LISTING_BATCH, len(pending), MAX_LISTINGS - listings)
            batch = [pending.popleft() for _ in range(size)]
            payloads = await asyncio.gather(
                *(
                    client.call("listfolder", {"path": folder}, context=folder)
                    for folder, _ in batch
                )
            )
            listings += size
            for (folder, depth), payload in zip(batch, payloads, strict=True):
                self.collect(
                    payload.get("metadata", {}).get("contents", []), folder, depth, pending
                )
                if self.truncated:
                    return

    def collect(
        self,
        contents: list[dict[str, Any]],
        folder: str,
        depth: int,
        pending: deque[tuple[str, int]],
    ) -> None:
        """Record name matches in one listing and queue its subfolders."""
        for item in contents:
            name = str(item.get("name", ""))
            path = str(item.get("path") or f"{folder.rstrip('/')}/{name}")
            if self.needle in name.lower():
                if len(self.matches) >= MAX_RESULTS:
                    self.truncated = True
                    return
                self.matches.append({**item, "path": path})
            if not item.get("isfolder"):
                continue
            if depth >= MAX_DEPTH:
                self.too_deep = True
            else:
                pending.append((path, depth + 1))


async def search(query: str, path: str) -> str:
    """Search for files and folders by name under a folder.

    pCloud has no usable name-search method, and a recursive listfolder fails
    at the root and outgrows the response size limit on large folders. This
    walks ``path`` breadth-first with one non-recursive listfolder per folder,
    up to ``LISTING_BATCH`` in flight at once, and matches names
    case-insensitively by substring, bounded by depth, result count and number
    of listings.
    """
    walk = _Walk(query.lower())
    await walk.run(path)
    header = f"Search results for '{query}' under {path}:"
    out = format_listing(walk.matches, header)
    if walk.truncated:
        out += f"\n\n(truncated at {MAX_RESULTS} results; narrow the query or path)"
    if walk.too_deep:
        out += f"\n\n(folders deeper than {MAX_DEPTH} levels were not searched)"
    if walk.out_of_listings:
        out += f"\n\n(stopped after listing {MAX_LISTINGS} folders; narrow the path)"
    return out

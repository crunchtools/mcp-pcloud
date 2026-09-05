"""Shared rendering helpers for pCloud metadata."""

from __future__ import annotations

from typing import Any

BYTES_PER_KB = 1024
BYTES_PER_GB = 1024 * 1024 * 1024


def format_entry(item: dict[str, Any]) -> str:
    """Render one file or folder metadata record as a text block."""
    name = item.get("name", "?")
    if item.get("isfolder"):
        return (
            f"[folder] {name}/\n"
            f"   Path: {item.get('path', '')}\n"
            f"   Modified: {item.get('modified', '')}"
        )
    size_kb = int(item.get("size", 0)) / BYTES_PER_KB
    return (
        f"[file] {name}\n"
        f"   Path: {item.get('path', '')}\n"
        f"   Size: {size_kb:.2f} KB\n"
        f"   Modified: {item.get('modified', '')}"
    )


def format_listing(entries: list[dict[str, Any]], header: str) -> str:
    """Render a list of metadata records under a header."""
    if not entries:
        return f"{header}\n\n(empty)"
    body = "\n\n".join(format_entry(entry) for entry in entries)
    return f"{header}\n\n{body}"

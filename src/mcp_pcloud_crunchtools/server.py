"""FastMCP server exposing pCloud tools.

This module only registers tools and validates arguments. All business
logic lives in tools/*.py.
"""

from __future__ import annotations

import logging

from fastmcp import FastMCP

from . import tools
from .errors import UserError
from .models import (
    DeleteFolderInput,
    ListFolderInput,
    MoveInput,
    PathInput,
    SearchInput,
)

logger = logging.getLogger(__name__)

mcp: FastMCP = FastMCP("mcp-pcloud-crunchtools", version="2.1.0")


def _safe(exc: UserError) -> str:
    """Render a user-safe error for return to the MCP client."""
    return f"Error: {exc}"


@mcp.tool()
async def pcloud_list_folder(path: str = "/", recursive: bool = False) -> str:
    """List contents of a folder in pCloud with file and folder metadata."""
    try:
        args = ListFolderInput(path=path, recursive=recursive)
        return await tools.list_folder(args.path, args.recursive)
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_create_folder(path: str) -> str:
    """Create a folder in pCloud, succeeding if it already exists."""
    try:
        args = PathInput(path=path)
        return await tools.create_folder(args.path)
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_delete_folder(path: str, recursive: bool = False) -> str:
    """Delete a folder in pCloud. Set recursive to remove its contents too."""
    try:
        args = DeleteFolderInput(path=path, recursive=recursive)
        return await tools.delete_folder(args.path, args.recursive)
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_rename_folder(path: str, to_path: str) -> str:
    """Rename or move a folder in pCloud."""
    try:
        args = MoveInput(path=path, to_path=to_path)
        return await tools.rename_folder(args.path, args.to_path)
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_copy_folder(path: str, to_path: str) -> str:
    """Copy a folder in pCloud to a new location."""
    try:
        args = MoveInput(path=path, to_path=to_path)
        return await tools.copy_folder(args.path, args.to_path)
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_get_file_info(path: str) -> str:
    """Get metadata for a file in pCloud."""
    try:
        args = PathInput(path=path)
        return await tools.get_file_info(args.path)
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_delete_file(path: str) -> str:
    """Delete a file from pCloud."""
    try:
        args = PathInput(path=path)
        return await tools.delete_file(args.path)
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_rename_file(path: str, to_path: str) -> str:
    """Rename or move a file in pCloud."""
    try:
        args = MoveInput(path=path, to_path=to_path)
        return await tools.rename_file(args.path, args.to_path)
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_copy_file(path: str, to_path: str) -> str:
    """Copy a file in pCloud to a new location."""
    try:
        args = MoveInput(path=path, to_path=to_path)
        return await tools.copy_file(args.path, args.to_path)
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_read_text_file(path: str) -> str:
    """Read the contents of a UTF-8 text file stored in pCloud."""
    try:
        args = PathInput(path=path)
        return await tools.read_text_file(args.path)
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_get_checksum(path: str) -> str:
    """Get pCloud's stored SHA256, SHA1, and MD5 checksums for a file."""
    try:
        args = PathInput(path=path)
        return await tools.get_checksum(args.path)
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_get_file_link(path: str) -> str:
    """Get a temporary direct download URL for a file in pCloud."""
    try:
        args = PathInput(path=path)
        return await tools.get_file_link(args.path)
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_create_public_link(path: str) -> str:
    """Create a public share link for a file, exposing it to anyone with the URL."""
    try:
        args = PathInput(path=path)
        return await tools.create_public_link(args.path)
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_search(query: str, path: str = "/") -> str:
    """Search pCloud for files and folders whose names match a query."""
    try:
        args = SearchInput(query=query, path=path)
        return await tools.search(args.query, args.path)
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_get_user_info() -> str:
    """Get the authenticated pCloud account's profile and quota usage."""
    try:
        return await tools.get_user_info()
    except UserError as exc:
        return _safe(exc)

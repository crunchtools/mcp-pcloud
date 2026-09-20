"""FastMCP server exposing pCloud tools.

This module only registers tools and validates arguments. All business
logic lives in tools/*.py.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastmcp import FastMCP
from starlette.responses import HTMLResponse

from . import tools
from .errors import UserError
from .models import (
    DeleteFolderInput,
    ListFolderInput,
    MoveInput,
    PathInput,
    SearchInput,
)

if TYPE_CHECKING:
    from starlette.requests import Request

logger = logging.getLogger(__name__)

mcp: FastMCP = FastMCP("mcp-pcloud-crunchtools", version="2.5.0")


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


@mcp.tool()
async def pcloud_auth_status() -> str:
    """Report whether this server currently holds a usable pCloud credential.

    Call this first. It says whether the server can reach pCloud, and if it
    cannot, what is missing and which tool fixes it.
    """
    try:
        return await tools.auth_status()
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_auth_start() -> str:
    """Begin browser authorization and return the URL for the user to approve.

    Open the returned URL. The user approves there, pCloud redirects back to
    this server, and the token is stored automatically -- nothing is copied
    back by hand. Then call pcloud_auth_status to confirm.
    """
    try:
        return await tools.auth_start()
    except UserError as exc:
        return _safe(exc)


@mcp.tool()
async def pcloud_auth_result() -> str:
    """Report the outcome of the most recent authorization redirect."""
    try:
        return await tools.auth_result()
    except UserError as exc:
        return _safe(exc)


@mcp.custom_route("/callback", methods=["GET"])
async def oauth_callback(request: Request) -> HTMLResponse:
    """Receive pCloud's redirect and finish the authorization.

    This is the whole reason the flow needs no copy and paste: pCloud sends
    the browser here, and the exchange happens server-side before the page
    renders. The response is read by a human, so it says what happened in
    plain words and never echoes a credential.
    """
    from .auth import complete_login, get_pending_login
    from .config import get_config

    params = request.query_params
    error = params.get("error")
    code = params.get("code")

    if error or not code:
        detail = error or "pCloud returned no authorization code"
        get_pending_login().record(f"Authorization failed: {detail}")
        return HTMLResponse(_callback_page("Authorization failed", detail), status_code=400)

    try:
        config = get_config()
        redirect_uri = config.oauth_redirect_uri or ""
        token_data = complete_login(
            config.client_id,
            config.client_secret,
            config.token_store,
            code=code,
            state=params.get("state"),
            hostname=params.get("hostname"),
            redirect_uri=redirect_uri,
        )
    except UserError as exc:
        get_pending_login().record(f"Authorization failed: {exc}")
        return HTMLResponse(_callback_page("Authorization failed", str(exc)), status_code=400)

    summary = f"Token stored. Region {token_data.api_host}, uid {token_data.uid}."
    get_pending_login().record(f"Authorization succeeded. {summary}")
    logger.info("Browser authorization completed")
    return HTMLResponse(_callback_page("pCloud authorization complete", "You can close this tab."))


def _callback_page(heading: str, detail: str) -> str:
    """Render the minimal page a human sees after being redirected back."""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{heading}</title></head>"
        "<body style='font-family:system-ui;max-width:34rem;margin:4rem auto'>"
        f"<h2>{heading}</h2><p>{detail}</p></body></html>"
    )

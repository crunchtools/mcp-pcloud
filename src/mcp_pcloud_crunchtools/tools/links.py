"""Download and public-share link operations."""

from __future__ import annotations

from ..client import get_client
from ..errors import PCloudApiError


async def get_file_link(path: str) -> str:
    """Return a temporary direct download URL for a file.

    The link is issued by pCloud, is time limited, and grants access to
    whoever holds it -- treat it as a credential.
    """
    payload = await get_client().call("getfilelink", {"path": path}, context=path)
    hosts = payload.get("hosts") or []
    link_path = payload.get("path")
    if not hosts or not link_path:
        raise PCloudApiError(0, "pCloud returned no download host for the file")
    return f"Temporary download link for {path}:\nhttps://{hosts[0]}{link_path}"


async def create_public_link(path: str) -> str:
    """Create a public share link for a file.

    This publishes the file to anyone holding the URL.
    """
    payload = await get_client().call(
        "getfilepublink", {"path": path}, context=path
    )
    link = payload.get("link")
    if not link:
        raise PCloudApiError(0, "pCloud returned no public link")
    return f"Public link for {path}:\n{link}"

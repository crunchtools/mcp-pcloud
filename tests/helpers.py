"""Mocked httpx plumbing shared by tool tests."""

from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx


def mock_response(payload: dict[str, Any], status_code: int = 200) -> httpx.Response:
    """Build an httpx.Response carrying a JSON payload."""
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("GET", "https://api.pcloud.com/test"),
    )


def text_response(body: str, status_code: int = 200) -> httpx.Response:
    """Build an httpx.Response carrying a plain-text body."""
    return httpx.Response(
        status_code=status_code,
        text=body,
        request=httpx.Request("GET", "https://api.pcloud.com/test"),
    )


@contextmanager
def patch_client(*responses: httpx.Response):
    """Patch httpx.AsyncClient.get to return the given responses in order."""
    mock_get = AsyncMock(side_effect=list(responses))
    with patch.object(httpx.AsyncClient, "get", mock_get):
        yield mock_get

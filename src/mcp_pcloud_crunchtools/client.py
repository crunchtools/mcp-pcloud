"""pCloud API client with security hardening.

All pCloud HTTP traffic goes through this client so authentication,
timeouts, TLS validation, and response limits are applied consistently.
"""

import logging
from typing import Any

import httpx

from .config import get_config
from .errors import (
    PCLOUD_ACCESS_DENIED,
    PCLOUD_DIR_NOT_FOUND,
    PCLOUD_FILE_NOT_FOUND,
    PCLOUD_INVALID_ACCESS_TOKEN,
    PCLOUD_INVALID_TOKEN,
    PCLOUD_LOGIN_REQUIRED,
    PCLOUD_RATE_LIMIT,
    PCLOUD_TWO_FACTOR_REQUIRED,
    AuthenticationError,
    PathNotFoundError,
    PCloudApiError,
    PermissionDeniedError,
    RateLimitError,
    TwoFactorRequiredError,
)

logger = logging.getLogger(__name__)

MAX_RESPONSE_SIZE = 10 * 1024 * 1024
REQUEST_TIMEOUT = 30.0
PCLOUD_OK = 0


class PCloudClient:
    """Async HTTP client for the pCloud API.

    Security properties:
    - OAuth token sent in the Authorization header, never in the URL
    - Session token sent in a POST body, never in the URL
    - TLS certificate validation left at httpx defaults (always on)
    - Request timeout and response size ceiling enforced
    - pCloud result codes mapped onto the safe error hierarchy
    """

    def __init__(self) -> None:
        """Initialize the client without opening a connection."""
        self._config = get_config()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Return the shared async client, creating it on first use.

        An OAuth token becomes a standing Authorization header. A session
        token carries per-request in the POST body instead, so no
        credential header is set here.
        """
        if self._client is None:
            headers = {"Accept": "application/json"}
            if self._config.uses_oauth:
                headers["Authorization"] = f"Bearer {self._config.access_token}"
            self._client = httpx.AsyncClient(
                base_url=self._config.api_base_url,
                headers=headers,
                timeout=httpx.Timeout(REQUEST_TIMEOUT),
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _raise_for_result(self, code: int, message: str, context: str) -> None:
        """Translate a pCloud result code into a safe user-facing error."""
        if code in (
            PCLOUD_LOGIN_REQUIRED,
            PCLOUD_INVALID_TOKEN,
            PCLOUD_INVALID_ACCESS_TOKEN,
        ):
            raise AuthenticationError(message)
        if code == PCLOUD_TWO_FACTOR_REQUIRED:
            raise TwoFactorRequiredError()
        if code in (PCLOUD_DIR_NOT_FOUND, PCLOUD_FILE_NOT_FOUND):
            raise PathNotFoundError(context)
        if code == PCLOUD_ACCESS_DENIED:
            raise PermissionDeniedError(context)
        if code == PCLOUD_RATE_LIMIT:
            raise RateLimitError()
        raise PCloudApiError(code, message)

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        context: str = "",
    ) -> dict[str, Any]:
        """Call a pCloud API method and return its decoded payload.

        Args:
            method: pCloud API method name, e.g. ``listfolder``.
            params: Query parameters for the call.
            context: Caller-supplied path used in not-found errors.

        Returns:
            The decoded JSON response.

        Raises:
            AuthenticationError: Token missing, expired, or rejected.
            PathNotFoundError: Target file or folder does not exist.
            PermissionDeniedError: Account lacks access to the target.
            RateLimitError: pCloud rate limit exceeded.
            PCloudApiError: Any other non-zero pCloud result code.

        """
        client = await self._get_client()
        logger.debug("pCloud request: %s", method)

        try:
            if self._config.uses_oauth:
                response = await client.get(f"/{method}", params=params or {})
            else:
                form = dict(params or {})
                form["auth"] = self._config.auth_token
                response = await client.post(f"/{method}", data=form)
        except httpx.TimeoutException as exc:
            raise PCloudApiError(0, f"Request to {method} timed out") from exc
        except httpx.HTTPError as exc:
            raise PCloudApiError(0, f"Request to {method} failed: {exc}") from exc

        if response.status_code in (401, 403):
            raise AuthenticationError(f"HTTP {response.status_code} from pCloud")
        if response.status_code >= 400:
            raise PCloudApiError(
                response.status_code, f"HTTP error from {method}"
            )

        if len(response.content) > MAX_RESPONSE_SIZE:
            raise PCloudApiError(0, f"Response from {method} exceeded size limit")

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise PCloudApiError(0, f"Malformed JSON from {method}") from exc

        result = int(payload.get("result", PCLOUD_OK))
        if result != PCLOUD_OK:
            self._raise_for_result(result, str(payload.get("error", "")), context)

        return payload

    async def fetch_text(self, url: str) -> str:
        """Download a text document from a pCloud-issued content URL.

        pCloud returns a host plus path for file content; the caller
        assembles the URL and passes it here so the size ceiling and
        timeout still apply.
        """
        client = await self._get_client()
        try:
            response = await client.get(url, headers={"Accept": "text/plain"})
        except httpx.HTTPError as exc:
            raise PCloudApiError(0, f"Content fetch failed: {exc}") from exc

        if response.status_code >= 400:
            raise PCloudApiError(response.status_code, "Content fetch failed")
        if len(response.content) > MAX_RESPONSE_SIZE:
            raise PCloudApiError(0, "File content exceeded size limit")
        return response.text


_client: PCloudClient | None = None


def get_client() -> PCloudClient:
    """Return the process-wide pCloud client, creating it on first use."""
    global _client
    if _client is None:
        _client = PCloudClient()
    return _client

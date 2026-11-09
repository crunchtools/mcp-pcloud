"""pCloud API client with security hardening.

All pCloud HTTP traffic goes through this client so authentication,
timeouts, TLS validation, and response limits are applied consistently.
"""

import json
import logging
from importlib.metadata import version
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
BODY_SNIPPET_CHARS = 200
ELLIPSIS = "..."

# Identify this client by name. httpx otherwise sends `python-httpx/<version>`,
# which bot protection answers with an HTML challenge page instead of the API --
# the failure that cost an afternoon on mcp-wordpress (RT #1596). The version
# comes from installed package metadata so it cannot drift from pyproject.toml.
USER_AGENT = (
    f"mcp-pcloud-crunchtools/{version('mcp-pcloud-crunchtools')} "
    "(+https://github.com/crunchtools/mcp-pcloud)"
)

# A pCloud content URL is signed: the host and path are issued per download and
# the `code` is the signature. Naming the URL in an error is the point of the
# third MUST, so these are taken out of it rather than the URL being left out.
REDACTED_PARAMS = frozenset(
    {"access_token", "auth", "client_secret", "code", "key", "password", "sig", "token"}
)


def _safe_url(url: httpx.URL) -> httpx.URL:
    """The URL as it can be shown: no userinfo, no credential query values."""
    url = url.copy_with(userinfo=b"")
    for name in REDACTED_PARAMS & set(url.params):
        url = url.copy_set_param(name, "***")
    return url


def _body_snippet(body: bytes) -> str:
    """A short, single-line excerpt of a response body, for an error message."""
    prefix = body[: BODY_SNIPPET_CHARS * 4]
    collapsed = " ".join(prefix.decode("utf-8", errors="replace").split())
    if not collapsed:
        return "<empty body>"
    if len(collapsed) > BODY_SNIPPET_CHARS or len(body) > len(prefix):
        return collapsed[: BODY_SNIPPET_CHARS - len(ELLIPSIS)] + ELLIPSIS
    return collapsed


def _where(response: httpx.Response) -> str:
    """Which request a response answered, for an error message.

    The URL actually requested, which is the half of RT #1596 that cost the
    time: a challenge page or an SSO interstitial answers from somewhere else
    entirely, and a bare status code cannot describe that.
    """
    return (
        f"{response.request.method} {_safe_url(response.request.url)} "
        f"(HTTP {response.status_code}, {response.headers.get('content-type', 'no content-type')})"
    )


async def _read_capped(response: httpx.Response) -> bytes:
    """Read the body, aborting as soon as it would pass MAX_RESPONSE_SIZE.

    The limit used to be `len(response.content) > MAX_RESPONSE_SIZE`, which
    compared the size once the whole body was already in the process -- the
    memory it exists to protect had been spent by the time it looked. Measured
    before each chunk is copied in, because `aiter_bytes()` promises nothing
    about chunk size: one chunk can be the whole body.
    """
    declared = response.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_RESPONSE_SIZE:
        raise PCloudApiError(
            response.status_code,
            f"{_where(response)} declared {declared} bytes, over the "
            f"{MAX_RESPONSE_SIZE} byte limit",
        )
    body = bytearray()
    async for chunk in response.aiter_bytes():
        if len(body) + len(chunk) > MAX_RESPONSE_SIZE:
            raise PCloudApiError(
                response.status_code,
                f"{_where(response)} sent over the {MAX_RESPONSE_SIZE} byte limit",
            )
        body += chunk
    return bytes(body)


async def _send(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> tuple[httpx.Response, bytes]:
    """Send one request and return it with its bounded body.

    One way out of this module, so neither of the two read paths -- the API and
    a content download -- can be the one that forgets the ceiling.
    """
    request = client.build_request(method, url, params=params, data=data)
    try:
        response = await client.send(request, stream=True)
        try:
            body = await _read_capped(response)
        finally:
            await response.aclose()
    # The URL is named here too, not only on an HTTP status: httpx's own
    # exception message does not reliably carry it, and a timeout with no
    # endpoint in it is the hardest of the three failures to place.
    except httpx.TimeoutException as exc:
        raise PCloudApiError(0, f"{method} {_safe_url(request.url)} timed out: {exc}") from exc
    except httpx.HTTPError as exc:
        raise PCloudApiError(0, f"{method} {_safe_url(request.url)} failed: {exc}") from exc
    return response, body


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
        self._content_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Return the shared async client, creating it on first use.

        An OAuth token becomes a standing Authorization header. A session
        token carries per-request in the POST body instead, so no
        credential header is set here.
        """
        if self._client is None:
            headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
            if self._config.uses_oauth:
                headers["Authorization"] = f"Bearer {self._config.access_token}"
            self._client = httpx.AsyncClient(
                base_url=self._config.api_base_url,
                headers=headers,
                timeout=httpx.Timeout(REQUEST_TIMEOUT),
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP clients."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._content_client is not None:
            await self._content_client.aclose()
            self._content_client = None

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

        if self._config.uses_oauth:
            response, body = await _send(client, "GET", f"/{method}", params=params or {})
        else:
            # A session token travels in the POST body, never in the URL, so
            # this path cannot become a GET for the sake of one code path.
            form = dict(params or {})
            form["auth"] = self._config.auth_token
            response, body = await _send(client, "POST", f"/{method}", data=form)

        if response.status_code in (401, 403):
            raise AuthenticationError(_where(response))
        if response.status_code >= 400:
            raise PCloudApiError(
                response.status_code, f"{_where(response)} returned {_body_snippet(body)}"
            )

        try:
            payload: dict[str, Any] = json.loads(body)
        except ValueError as exc:
            # The RT #1596 shape: a challenge page or an SSO interstitial is
            # valid HTTP and invalid JSON, and `Malformed JSON from listfolder`
            # gave a reader nothing to act on.
            raise PCloudApiError(
                0, f"{_where(response)} is not JSON: {_body_snippet(body)}"
            ) from exc

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
        # Content URLs are already signed, so this client has no base URL
        # and never carries the API credential.
        if self._content_client is None:
            self._content_client = httpx.AsyncClient(
                timeout=httpx.Timeout(REQUEST_TIMEOUT),
                headers={"Accept": "text/plain", "User-Agent": USER_AGENT},
            )
        client = self._content_client
        response, body = await _send(client, "GET", url)

        if response.status_code >= 400:
            raise PCloudApiError(
                response.status_code, f"{_where(response)} returned {_body_snippet(body)}"
            )
        # The charset the response declared, not a hardcoded UTF-8: this
        # replaced `response.text`, which honoured it, and a Latin-1 document
        # silently decoded as UTF-8 comes back with replacement characters
        # where its accents were. httpx reads this from the header alone and
        # falls back to UTF-8, which is what a pCloud text file is in practice.
        return body.decode(response.encoding or "utf-8", errors="replace")


_client: PCloudClient | None = None


def get_client() -> PCloudClient:
    """Return the process-wide pCloud client, creating it on first use."""
    global _client
    if _client is None:
        _client = PCloudClient()
    return _client

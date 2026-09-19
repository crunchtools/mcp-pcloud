"""OAuth 2.0 authorization code flow and token persistence.

pCloud's OAuth differs from most providers in two ways that shape this
module:

1. ``oauth2_token`` returns only ``access_token``, ``token_type`` and
   ``uid``. There is no ``refresh_token`` and no ``expires_in``, so there
   is no refresh cycle to implement -- a token stays valid until it is
   revoked from the pCloud app console. Revocation surfaces as a pCloud
   result code, which the client maps to AuthenticationError.

2. The authorize redirect carries ``hostname`` and ``locationid``,
   identifying the data center holding the account. That hostname is
   persisted alongside the token so the region never has to be guessed or
   configured by hand.

The client secret is only ever sent in a POST body, never in a URL, which
is the property the security model defends.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import stat
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from pydantic import BaseModel, SecretStr

from .errors import AuthenticationError, TokenUnavailableError, register_secret

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_STORE_PATH = Path.home() / ".config" / "mcp-pcloud" / "tokens.json"
DEFAULT_CALLBACK_PORT = 8029
TOKEN_STORE_PATH_VAR = "PCLOUD_TOKEN_STORE_PATH"

OAUTH_AUTHORIZE_URL = "https://my.pcloud.com/oauth2/authorize"

US_API_HOST = "api.pcloud.com"
EU_API_HOST = "eapi.pcloud.com"
VALID_API_HOSTS = (US_API_HOST, EU_API_HOST)

HTTP_TIMEOUT = 30.0
HTTP_OK = 200
PCLOUD_OK = 0


class TokenData(BaseModel):
    """A pCloud bearer token and the region that issued it.

    There is deliberately no ``expires_at``: pCloud does not time-limit
    access tokens and returns no expiry to record. Inventing one would
    mean expiring a credential that is still perfectly valid.
    """

    access_token: SecretStr
    api_host: str = US_API_HOST
    uid: int | None = None


class TokenStore:
    """Read and write the pCloud bearer token in a local JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        """Resolve the store location from the environment, argument, or default."""
        env_path = os.environ.get(TOKEN_STORE_PATH_VAR)
        if env_path:
            self._path = Path(env_path)
        elif path is not None:
            self._path = path
        else:
            self._path = DEFAULT_TOKEN_STORE_PATH
        self._cached: TokenData | None = None

    @property
    def path(self) -> Path:
        """Return the filesystem path backing this store."""
        return self._path

    def load(self) -> TokenData | None:
        """Return the stored token, or None when absent or unreadable."""
        if not self._path.exists():
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            host = str(raw.get("api_host", US_API_HOST))
            if host not in VALID_API_HOSTS:
                host = US_API_HOST
            uid_raw = raw.get("uid")
            self._cached = TokenData(
                access_token=SecretStr(raw["access_token"]),
                api_host=host,
                uid=int(uid_raw) if uid_raw is not None else None,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, OSError) as exc:
            logger.warning("Could not load tokens from %s: %s", self._path, exc)
            return None
        else:
            register_secret(self._cached.access_token.get_secret_value())
            return self._cached

    def save(self, token_data: TokenData) -> None:
        """Write the token to disk, creating the file 0600."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "access_token": token_data.access_token.get_secret_value(),
                "api_host": token_data.api_host,
                "uid": token_data.uid,
            },
            indent=2,
        )
        fd = os.open(
            str(self._path),
            os.O_CREAT | os.O_WRONLY | os.O_TRUNC,
            stat.S_IRUSR | stat.S_IWUSR,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
        except Exception:
            os.close(fd)
            raise
        self._cached = token_data
        register_secret(token_data.access_token.get_secret_value())
        logger.info("Token saved to %s", self._path)

    def get_token(self) -> TokenData:
        """Return the stored token.

        Raises:
            TokenUnavailableError: If no token has been stored yet.
        """
        if self._cached is None:
            self._cached = self.load()
        if self._cached is None:
            raise TokenUnavailableError(str(self._path))
        return self._cached


class _CallbackHandler(BaseHTTPRequestHandler):
    """Capture pCloud's redirect and stash its parameters on the server."""

    def do_GET(self) -> None:
        """Record the callback query string and tell the browser it is done."""
        params = parse_qs(urlparse(self.path).query)
        server = cast("_CallbackServer", self.server)

        def first(key: str) -> str | None:
            values = params.get(key, [])
            return values[0] if values else None

        server.callback_code = first("code")
        server.callback_state = first("state")
        server.callback_error = first("error")
        server.callback_hostname = first("hostname")

        self.send_response(HTTP_OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body style='font-family:sans-serif'>"
            b"<h2>pCloud authorization complete</h2>"
            b"<p>You can close this tab and return to the terminal.</p>"
            b"</body></html>"
        )
        Thread(target=server.shutdown, daemon=True).start()

    def log_message(self, format: str, *args: Any) -> None:
        """Silence the default stderr request logging."""


class _CallbackServer(HTTPServer):
    """HTTPServer with slots for the OAuth callback parameters."""

    callback_code: str | None = None
    callback_state: str | None = None
    callback_error: str | None = None
    callback_hostname: str | None = None


def run_login_flow(
    client_id: str,
    client_secret: SecretStr,
    token_store: TokenStore,
    callback_port: int = DEFAULT_CALLBACK_PORT,
    open_browser: bool = True,
) -> TokenData:
    """Run the OAuth 2.0 authorization code flow and persist the result.

    Args:
        client_id: The pCloud application's client id.
        client_secret: The application's client secret.
        token_store: Where the resulting token is written.
        callback_port: Local port to receive pCloud's redirect on.
        open_browser: Whether to launch a browser automatically. Set False
            on headless hosts, where the URL is printed instead.

    Returns:
        The token that was obtained and saved.

    Raises:
        AuthenticationError: If pCloud denies the request, the CSRF state
            does not match, or the code exchange fails.
    """
    redirect_uri = f"http://localhost:{callback_port}/callback"
    state = secrets.token_urlsafe(32)

    params = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    auth_url = f"{OAUTH_AUTHORIZE_URL}?{params}"

    server = _CallbackServer(("127.0.0.1", callback_port), _CallbackHandler)

    print(f"Listening for pCloud's redirect on {redirect_uri}")
    print(f"\nOpen this URL and approve the app:\n\n  {auth_url}\n")
    if open_browser:
        webbrowser.open(auth_url)

    print("Waiting for the callback...")
    server.serve_forever()

    if server.callback_error:
        raise AuthenticationError(f"pCloud denied authorization: {server.callback_error}")
    if server.callback_code is None:
        raise AuthenticationError("No authorization code arrived in the callback")
    if not secrets.compare_digest(server.callback_state or "", state):
        raise AuthenticationError("State parameter mismatch -- possible CSRF, aborting")

    # pCloud reports which data center holds the account. Trust it over any
    # configured default, but never trust it blindly.
    api_host = server.callback_hostname or US_API_HOST
    if api_host not in VALID_API_HOSTS:
        logger.warning("Ignoring unrecognized callback hostname %r", api_host)
        api_host = US_API_HOST

    print(f"Exchanging the authorization code on {api_host}...")
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, verify=True) as http:
            response = http.post(
                f"https://{api_host}/oauth2_token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret.get_secret_value(),
                    "code": server.callback_code,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise AuthenticationError(
            f"Token exchange failed with HTTP {exc.response.status_code}"
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise AuthenticationError(f"Token exchange failed: {exc}") from exc

    # pCloud signals failure with a non-zero ``result`` field rather than
    # an HTTP status, so a 200 response still has to be inspected.
    result_code = int(payload.get("result", PCLOUD_OK))
    if result_code != PCLOUD_OK:
        raise AuthenticationError(
            f"pCloud rejected the authorization code "
            f"(result {result_code}): {payload.get('error', '')}"
        )

    access_token = payload.get("access_token")
    if not access_token:
        raise AuthenticationError("Token response contained no access_token")

    uid_raw = payload.get("uid")
    token_data = TokenData(
        access_token=SecretStr(str(access_token)),
        api_host=api_host,
        uid=int(uid_raw) if uid_raw is not None else None,
    )
    token_store.save(token_data)
    print(f"\nLogin successful. Token saved to {token_store.path}")
    print(f"Region: {token_data.api_host}")
    return token_data

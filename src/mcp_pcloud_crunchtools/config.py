"""Secure configuration handling.

pCloud credentials are held as Pydantic SecretStr values so they are never
logged or exposed through repr/str.

Three authentication modes are supported, in descending preference:

``OAUTH_APP``
    ``PCLOUD_CLIENT_ID`` + ``PCLOUD_CLIENT_SECRET`` identify a registered
    pCloud application. The bearer token is obtained once by running
    ``mcp-pcloud-crunchtools login`` and is then read from the token
    store. This is the modern path: nothing has to be minted by hand, and
    the resulting credential is revocable from the pCloud app console
    without disturbing the account password or any other session.

``STATIC_TOKEN``
    ``PCLOUD_ACCESS_TOKEN`` supplies a bearer token directly. Useful for
    containers and CI, where running an interactive flow is impractical.

``SESSION_TOKEN``
    ``PCLOUD_AUTH_TOKEN`` supplies a pCloud desktop-client session token.
    It is a last resort: a session token *is* the account, and cannot be
    revoked independently of the client that issued it.

Every credential variable also honors a ``_FILE`` form, which takes
precedence and is preferred for container deployments.
"""

from __future__ import annotations

import enum
import logging
import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import SecretStr

from .errors import ConfigurationError

if TYPE_CHECKING:
    from .auth import TokenStore

logger = logging.getLogger(__name__)

US_API_HOST = "api.pcloud.com"
EU_API_HOST = "eapi.pcloud.com"
VALID_API_HOSTS = (US_API_HOST, EU_API_HOST)

SECRET_FILE_MODE_MASK = 0o077

OAUTH_VAR = "PCLOUD_ACCESS_TOKEN"
SESSION_VAR = "PCLOUD_AUTH_TOKEN"
CLIENT_ID_VAR = "PCLOUD_CLIENT_ID"
CLIENT_SECRET_VAR = "PCLOUD_CLIENT_SECRET"
API_HOST_VAR = "PCLOUD_API_HOST"


class AuthMode(enum.Enum):
    """How this process authenticates to pCloud."""

    OAUTH_APP = "oauth_app"
    STATIC_TOKEN = "static_token"
    SESSION_TOKEN = "session_token"


def _read_credential(name: str) -> str | None:
    """Resolve a credential from ``<NAME>_FILE`` or ``<NAME>``.

    The ``_FILE`` form takes precedence: it is the preferred mechanism for
    container deployments (podman secrets, Kubernetes secret volumes,
    systemd LoadCredential=). A secret file readable beyond its owner is
    warned about but still accepted.

    Raises:
        ConfigurationError: If the referenced file is unreadable or empty.
    """
    file_var = f"{name}_FILE"
    path_value = os.environ.get(file_var)
    if path_value:
        path = Path(path_value)
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigurationError(
                f"Could not read {file_var}: {exc.strerror or 'unreadable'}"
            ) from exc
        if not value:
            raise ConfigurationError(f"{file_var} points at an empty file")
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            mode = 0
        if mode & SECRET_FILE_MODE_MASK:
            logger.warning("Secret file %s is group/world accessible; tighten to 0600", path)
        return value

    direct = os.environ.get(name, "").strip()
    return direct or None


class Config:
    """Configuration loaded from environment variables."""

    def __init__(self) -> None:
        """Resolve the authentication mode and the API region endpoint.

        Raises:
            ConfigurationError: If no credential is available, a secret
                file is empty or unreadable, or the API host is not a
                recognized pCloud region endpoint.
        """
        self._token_store: TokenStore | None = None
        self._client_id: str | None = None
        self._client_secret: SecretStr | None = None
        self._access_token: SecretStr | None = None
        self._auth_token: SecretStr | None = None

        client_id = _read_credential(CLIENT_ID_VAR)
        client_secret = _read_credential(CLIENT_SECRET_VAR)
        oauth = _read_credential(OAUTH_VAR)
        session = _read_credential(SESSION_VAR)

        if client_id and client_secret:
            from .auth import TokenStore

            self._mode = AuthMode.OAUTH_APP
            self._client_id = client_id
            self._client_secret = SecretStr(client_secret)
            self._token_store = TokenStore()
        elif oauth:
            self._mode = AuthMode.STATIC_TOKEN
            self._access_token = SecretStr(oauth)
        elif session:
            self._mode = AuthMode.SESSION_TOKEN
            self._auth_token = SecretStr(session)
        else:
            raise ConfigurationError(
                "pCloud authentication required. Choose one:\n"
                f"  OAuth app (preferred): set {CLIENT_ID_VAR} + "
                f"{CLIENT_SECRET_VAR}, then run "
                "`mcp-pcloud-crunchtools login`\n"
                f"  Static token:          set {OAUTH_VAR}\n"
                f"  Session token:         set {SESSION_VAR}\n"
                "Any of these may use the _FILE form. Register an "
                "application at https://docs.pcloud.com/my_apps/ -- "
                "password authentication is not supported."
            )

        if client_id and client_secret and (oauth or session):
            logger.info("Multiple credentials present; the OAuth application wins")

        # An explicit region override, validated here so a bad value fails
        # at startup rather than on the first call.
        raw_host = os.environ.get(API_HOST_VAR, "").strip()
        if raw_host and raw_host not in VALID_API_HOSTS:
            raise ConfigurationError(
                f"Invalid {API_HOST_VAR}: must be one of {', '.join(VALID_API_HOSTS)}"
            )
        self._explicit_host = raw_host or None

        logger.info(
            "Configuration loaded successfully (pCloud: %s, auth: %s)",
            self.api_host,
            self._mode.value,
        )

    @property
    def mode(self) -> AuthMode:
        """Return the active authentication mode."""
        return self._mode

    @property
    def uses_oauth(self) -> bool:
        """Return True when calls carry an ``Authorization: Bearer`` header.

        Both the OAuth application and a directly supplied access token
        are bearer credentials. Only a session token is not.
        """
        return self._mode in (AuthMode.OAUTH_APP, AuthMode.STATIC_TOKEN)

    @property
    def client_id(self) -> str:
        """Return the pCloud application's client id.

        Raises:
            ConfigurationError: If no OAuth application is configured.
        """
        if self._client_id is None:
            raise ConfigurationError(f"{CLIENT_ID_VAR} is not configured")
        return self._client_id

    @property
    def client_secret(self) -> SecretStr:
        """Return the pCloud application's client secret.

        Raises:
            ConfigurationError: If no OAuth application is configured.
        """
        if self._client_secret is None:
            raise ConfigurationError(f"{CLIENT_SECRET_VAR} is not configured")
        return self._client_secret

    @property
    def token_store(self) -> TokenStore:
        """Return the token store backing OAuth application mode.

        Raises:
            ConfigurationError: If no OAuth application is configured.
        """
        if self._token_store is None:
            raise ConfigurationError(f"{CLIENT_ID_VAR} is not configured")
        return self._token_store

    @property
    def access_token(self) -> str:
        """Return the bearer token, for the Authorization header.

        In OAuth application mode this reads the stored token, which is
        written once by the login flow. pCloud does not expire tokens, so
        there is no refresh step here.

        Raises:
            ConfigurationError: If this mode has no bearer token.
            TokenUnavailableError: If login has not been run yet.
        """
        if self._mode is AuthMode.OAUTH_APP:
            return self.token_store.get_token().access_token.get_secret_value()
        if self._access_token is None:
            raise ConfigurationError(f"{OAUTH_VAR} is not configured")
        return self._access_token.get_secret_value()

    @property
    def auth_token(self) -> str:
        """Return the pCloud session token, for the POST body.

        Raises:
            ConfigurationError: If no session token is configured.
        """
        if self._auth_token is None:
            raise ConfigurationError(f"{SESSION_VAR} is not configured")
        return self._auth_token.get_secret_value()

    @property
    def api_host(self) -> str:
        """Return the pCloud API hostname for the account's region.

        An explicit ``PCLOUD_API_HOST`` always wins. Otherwise the region
        recorded by the login flow is used, falling back to the US
        endpoint when nothing is stored yet.
        """
        if self._explicit_host:
            return self._explicit_host
        if self._mode is AuthMode.OAUTH_APP and self._token_store is not None:
            stored = self._token_store.load()
            if stored is not None:
                return stored.api_host
        return US_API_HOST

    @property
    def api_base_url(self) -> str:
        """Return the HTTPS base URL for the pCloud API."""
        return f"https://{self.api_host}"

    def __repr__(self) -> str:
        """Return a safe repr that never exposes a credential."""
        return f"Config(api_host={self.api_host}, auth={self._mode.value}, token=***)"

    def __str__(self) -> str:
        """Return a safe str that never exposes a credential."""
        return self.__repr__()


_config: Config | None = None


def get_config() -> Config:
    """Return the process-wide configuration, initializing it on first use."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config() -> None:
    """Drop the cached configuration. Intended for tests and after login."""
    global _config
    _config = None

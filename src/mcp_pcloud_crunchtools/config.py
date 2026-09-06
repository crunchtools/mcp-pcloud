"""Secure configuration handling.

pCloud credentials are held as Pydantic SecretStr values so they are never
logged or exposed through repr/str. Two credential kinds are supported and
either may be supplied directly or, preferred for containers, via a
``_FILE`` variable pointing at a secret file.
"""

import logging
import os
import stat
from pathlib import Path

from pydantic import SecretStr

from .errors import ConfigurationError

logger = logging.getLogger(__name__)

US_API_HOST = "api.pcloud.com"
EU_API_HOST = "eapi.pcloud.com"
VALID_API_HOSTS = (US_API_HOST, EU_API_HOST)

SECRET_FILE_MODE_MASK = 0o077

OAUTH_VAR = "PCLOUD_ACCESS_TOKEN"
SESSION_VAR = "PCLOUD_AUTH_TOKEN"


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
            logger.warning(
                "Secret file %s is group/world accessible; tighten to 0600", path
            )
        return value

    direct = os.environ.get(name, "").strip()
    return direct or None


class Config:
    """Configuration loaded from environment variables."""

    def __init__(self) -> None:
        """Resolve credentials and the API region endpoint.

        An OAuth access token is preferred. A pCloud session token is
        accepted as a fallback for accounts that only have one; it is
        transmitted in a POST body rather than a URL.

        Raises:
            ConfigurationError: If neither credential is available, a token
                file is empty or unreadable, or the API host is not a
                recognized pCloud region endpoint.
        """
        oauth = _read_credential(OAUTH_VAR)
        session = _read_credential(SESSION_VAR)

        if not oauth and not session:
            raise ConfigurationError(
                f"{OAUTH_VAR} or {SESSION_VAR} required (either may use the "
                "_FILE form). Create an OAuth access token at "
                "https://docs.pcloud.com/my_apps/ -- password authentication "
                "is not supported."
            )

        if oauth and session:
            logger.info("Both credentials present; using the OAuth access token")

        self._access_token = SecretStr(oauth) if oauth else None
        self._auth_token = SecretStr(session) if session else None

        api_host = os.environ.get("PCLOUD_API_HOST", US_API_HOST).strip()
        if api_host not in VALID_API_HOSTS:
            raise ConfigurationError(
                f"Invalid PCLOUD_API_HOST: must be one of {', '.join(VALID_API_HOSTS)}"
            )
        self._api_host = api_host

        logger.info(
            "Configuration loaded successfully (pCloud: %s, auth: %s)",
            self._api_host,
            "oauth" if self.uses_oauth else "session",
        )

    @property
    def uses_oauth(self) -> bool:
        """Return True when an OAuth access token is configured.

        OAuth wins whenever both credential kinds are present.
        """
        return self._access_token is not None

    @property
    def access_token(self) -> str:
        """Return the OAuth access token, for the Authorization header.

        Raises:
            ConfigurationError: If no OAuth token is configured.
        """
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
        """Return the pCloud API hostname for the account's region."""
        return self._api_host

    @property
    def api_base_url(self) -> str:
        """Return the HTTPS base URL for the pCloud API."""
        return f"https://{self._api_host}"

    def __repr__(self) -> str:
        """Return a safe repr that never exposes a credential."""
        kind = "oauth" if self.uses_oauth else "session"
        return f"Config(api_host={self._api_host}, auth={kind}, token=***)"

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

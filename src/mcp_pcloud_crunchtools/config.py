"""Secure configuration handling.

The pCloud OAuth access token is stored as a SecretStr so it is never
logged or exposed through repr/str. Credentials may be supplied directly
via environment variable or, preferred for containers, via a ``_FILE``
variable pointing at a secret file.
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

TOKEN_VAR = "PCLOUD_ACCESS_TOKEN"
TOKEN_FILE_VAR = "PCLOUD_ACCESS_TOKEN_FILE"


class Config:
    """Configuration loaded from environment variables."""

    def __init__(self) -> None:
        """Resolve credentials and the API region endpoint.

        The ``_FILE`` credential form takes precedence over the direct
        environment variable: it is the preferred mechanism for container
        deployments (podman secrets, Kubernetes secret volumes, systemd
        LoadCredential=). A secret file readable beyond its owner is
        warned about but still accepted.

        Raises:
            ConfigurationError: If no token is available, the token file
                is empty or unreadable, or the API host is not a
                recognized pCloud region endpoint.
        """
        token_path = os.environ.get(TOKEN_FILE_VAR)
        if token_path:
            path = Path(token_path)
            try:
                token = path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ConfigurationError(
                    f"Could not read {TOKEN_FILE_VAR}: {exc.strerror or 'unreadable'}"
                ) from exc
            if not token:
                raise ConfigurationError(f"{TOKEN_FILE_VAR} points at an empty file")
            try:
                mode = stat.S_IMODE(path.stat().st_mode)
            except OSError:
                mode = 0
            if mode & SECRET_FILE_MODE_MASK:
                logger.warning(
                    "Secret file %s is group/world accessible; tighten to 0600", path
                )
        else:
            direct = os.environ.get(TOKEN_VAR, "")
            token = direct.strip()

        if not token:
            raise ConfigurationError(
                f"{TOKEN_VAR} (or {TOKEN_FILE_VAR}) required. "
                "Create an OAuth access token at https://docs.pcloud.com/my_apps/ "
                "-- password authentication is not supported."
            )
        self._access_token = SecretStr(token)

        api_host = os.environ.get("PCLOUD_API_HOST", US_API_HOST).strip()
        if api_host not in VALID_API_HOSTS:
            raise ConfigurationError(
                f"Invalid PCLOUD_API_HOST: must be one of {', '.join(VALID_API_HOSTS)}"
            )
        self._api_host = api_host

        logger.info("Configuration loaded successfully (pCloud: %s)", self._api_host)

    @property
    def access_token(self) -> str:
        """Return the OAuth access token, for building an Authorization header."""
        return self._access_token.get_secret_value()

    @property
    def api_host(self) -> str:
        """Return the pCloud API hostname for the account's region."""
        return self._api_host

    @property
    def api_base_url(self) -> str:
        """Return the HTTPS base URL for the pCloud API."""
        return f"https://{self._api_host}"

    def __repr__(self) -> str:
        """Return a safe repr that never exposes the token."""
        return f"Config(api_host={self._api_host}, access_token=***)"

    def __str__(self) -> str:
        """Return a safe str that never exposes the token."""
        return self.__repr__()


_config: Config | None = None


def get_config() -> Config:
    """Return the process-wide configuration, initializing it on first use."""
    global _config
    if _config is None:
        _config = Config()
    return _config

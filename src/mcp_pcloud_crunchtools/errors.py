"""Safe error types that can be shown to users.

This module defines exception classes that are safe to expose to MCP clients.
Internal errors should be caught and converted to UserError before propagating.
"""

import os

SAFE_ID_MAX_LENGTH = 40

PCLOUD_LOGIN_REQUIRED = 1000
PCLOUD_INVALID_TOKEN = 2000
PCLOUD_TWO_FACTOR_REQUIRED = 2297
PCLOUD_DIR_NOT_FOUND = 2005
PCLOUD_FILE_NOT_FOUND = 2009
PCLOUD_ACCESS_DENIED = 2003
PCLOUD_RATE_LIMIT = 4000


def _scrub(message: str) -> str:
    """Remove any configured credential value from a message."""
    safe = message
    for var in ("PCLOUD_ACCESS_TOKEN", "PCLOUD_CLIENT_SECRET"):
        secret = os.environ.get(var, "")
        if secret:
            safe = safe.replace(secret, "***")
    return safe


def _truncate(identifier: str) -> str:
    """Shorten an identifier so errors never echo long caller-supplied paths."""
    if len(identifier) > SAFE_ID_MAX_LENGTH:
        return identifier[:SAFE_ID_MAX_LENGTH] + "..."
    return identifier


class UserError(Exception):
    """Base class for safe errors that can be shown to users."""


class ConfigurationError(UserError):
    """Error in server configuration."""


class PCloudApiError(UserError):
    """Error returned by the pCloud API.

    The message is scrubbed to remove any credential values.
    """

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        super().__init__(f"pCloud API error {code}: {_scrub(message)}")


class AuthenticationError(UserError):
    """Access token missing, expired, or rejected by pCloud."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"pCloud authentication failed: {_scrub(detail)}. "
            "Set PCLOUD_ACCESS_TOKEN (or PCLOUD_ACCESS_TOKEN_FILE) to a valid "
            "OAuth access token."
        )


class TwoFactorRequiredError(UserError):
    """The account requires 2FA, which OAuth tokens satisfy but passwords do not."""

    def __init__(self) -> None:
        super().__init__(
            "pCloud requires two-factor authentication for this account. "
            "Password authentication cannot satisfy it -- supply an OAuth "
            "access token via PCLOUD_ACCESS_TOKEN."
        )


class PathNotFoundError(UserError):
    """A file or folder path does not exist."""

    def __init__(self, path: str) -> None:
        super().__init__(f"Path not found: {_truncate(path)}")


class PermissionDeniedError(UserError):
    """Access denied for the requested pCloud operation."""

    def __init__(self, path: str) -> None:
        super().__init__(f"Access denied for: {_truncate(path)}")


class RateLimitError(UserError):
    """pCloud rate limit exceeded."""

    def __init__(self) -> None:
        super().__init__("pCloud rate limit exceeded. Retry later.")


class ValidationError(UserError):
    """Input validation error."""

"""Authorization status and browser-based login, exposed as MCP tools.

The point of these is that re-authorizing a containerized server is a tool
call rather than a runbook. An agent asks whether the server is authorized,
opens the URL it hands back, and the user approves in a browser. pCloud
redirects to the server's own ``/callback`` route, which finishes the
exchange -- nothing is copied or pasted, and no shell is involved.
"""

from __future__ import annotations

from ..auth import build_authorize_url, get_pending_login
from ..client import get_client
from ..config import AuthMode, get_config
from ..errors import ConfigurationError, TokenUnavailableError, UserError


async def auth_status() -> str:
    """Report whether the server holds a usable pCloud credential.

    Answers the only question worth asking before doing work: can this
    server talk to pCloud right now, and if not, what is missing?
    """
    config = get_config()
    lines = [f"Auth mode: {config.mode.value}"]

    if config.mode is not AuthMode.OAUTH_APP:
        lines.append("Status: authorized (static credential supplied by configuration)")
        lines.append("Browser authorization does not apply to this mode.")
        return "\n".join(lines)

    lines.append(f"Token store: {config.token_store.path}")

    try:
        stored = config.token_store.get_token()
    except TokenUnavailableError:
        lines.append("Status: NOT AUTHORIZED -- no token stored")
        lines.append("Run the pcloud_auth_start tool to begin browser authorization.")
        return "\n".join(lines)

    lines.append(f"Region: {stored.api_host}")
    lines.append(f"pCloud uid: {stored.uid if stored.uid is not None else 'unknown'}")

    try:
        payload = await get_client().call("userinfo", context="account")
    except UserError as exc:
        lines.append(f"Status: token present but REJECTED by pCloud -- {exc}")
        lines.append("Run the pcloud_auth_start tool to authorize again.")
        return "\n".join(lines)

    lines.append("Status: authorized and verified against pCloud")
    lines.append(f"Account: {payload.get('email', '')}")
    return "\n".join(lines)


async def auth_start() -> str:
    """Begin browser authorization and return the URL to open.

    The caller opens the returned URL; the user approves there. pCloud then
    redirects to this server's ``/callback`` route, which completes the
    exchange and stores the token. Poll ``pcloud_auth_status`` afterwards to
    confirm.

    Raises:
        ConfigurationError: If the server is not in OAuth application mode,
            or has no public redirect URI configured.
    """
    config = get_config()

    if config.mode is not AuthMode.OAUTH_APP:
        raise ConfigurationError(
            f"Browser authorization needs OAuth application mode, but this "
            f"server is in {config.mode.value} mode. Set PCLOUD_CLIENT_ID "
            "and PCLOUD_CLIENT_SECRET."
        )

    redirect_uri = config.oauth_redirect_uri
    if not redirect_uri:
        raise ConfigurationError(
            "PCLOUD_OAUTH_REDIRECT_URI is not set. Browser authorization needs "
            "a URL pCloud can redirect to that reaches this server's /callback "
            "route -- for a container behind a reverse proxy, that is the "
            "public https URL."
        )

    url = build_authorize_url(config.client_id, get_pending_login().issue(), redirect_uri)
    return (
        "Open this URL in a browser and approve the application:\n\n"
        f"{url}\n\n"
        f"pCloud will redirect to {redirect_uri}, which this server handles "
        "directly. Nothing needs to be copied back.\n"
        "Then call pcloud_auth_status to confirm the token was stored.\n"
        "The authorization expires in 10 minutes if not completed."
    )


async def auth_result() -> str:
    """Return the outcome of the most recent browser redirect.

    Useful when ``pcloud_auth_status`` still reports no token: this says
    whether a redirect arrived at all and what pCloud said about it.
    """
    recorded = get_pending_login().outcome
    if recorded is None:
        return "No authorization redirect has been received since this server started."
    return recorded

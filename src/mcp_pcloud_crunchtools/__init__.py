r"""MCP pCloud CrunchTools - Secure MCP server for pCloud storage.

Usage:
    mcp-pcloud-crunchtools login      # authorize once via OAuth 2.0
    mcp-pcloud-crunchtools serve      # run the server (default)

    python -m mcp_pcloud_crunchtools

    uvx mcp-pcloud-crunchtools

Environment Variables:
    PCLOUD_CLIENT_ID, PCLOUD_CLIENT_SECRET: Preferred. Identify a pCloud
        application registered at https://docs.pcloud.com/my_apps/. Run
        `login` once; the resulting bearer token is cached in the token
        store and reused. pCloud does not expire access tokens, so there
        is nothing to renew until the app is revoked.
    PCLOUD_ACCESS_TOKEN: A bearer token supplied directly, for containers
        and CI where an interactive flow is impractical.
    PCLOUD_AUTH_TOKEN: A pCloud desktop-client session token. Last resort
        -- it is the account itself and cannot be revoked independently.
    PCLOUD_TOKEN_STORE_PATH: Override where the token is cached.
    PCLOUD_API_HOST: Optional. api.pcloud.com or eapi.pcloud.com. Normally
        discovered automatically during login.

    Every credential variable also honors a _FILE form, which takes
    precedence and is preferred for container deployments.

Example with Claude Code:
    claude mcp add mcp-pcloud-crunchtools \\
        --env PCLOUD_CLIENT_ID=your_client_id \\
        --env PCLOUD_CLIENT_SECRET=your_client_secret \\
        -- uvx mcp-pcloud-crunchtools
"""

import argparse
import sys

from .server import mcp

__version__ = "2.2.0"
__all__ = ["main", "mcp"]

DEFAULT_PORT = 8028
DEFAULT_CALLBACK_PORT = 8029


def _run_login(args: argparse.Namespace) -> None:
    """Handle the login subcommand."""
    from .auth import TokenStore, run_login_flow
    from .config import CLIENT_ID_VAR, CLIENT_SECRET_VAR, _read_credential
    from .errors import UserError

    client_id = _read_credential(CLIENT_ID_VAR)
    client_secret = _read_credential(CLIENT_SECRET_VAR)
    if not client_id or not client_secret:
        # The variable names are spelled out literally rather than
        # interpolated from CLIENT_ID_VAR/CLIENT_SECRET_VAR: a static
        # analyzer cannot tell a secret-named constant from a secret, and
        # reads the interpolation as logging one in clear text.
        print(
            "Error: PCLOUD_CLIENT_ID and PCLOUD_CLIENT_SECRET must both be "
            "set to log in.\nRegister an application at "
            "https://docs.pcloud.com/my_apps/ and add the redirect URI\n"
            f"  http://localhost:{args.port}/callback",
            file=sys.stderr,
        )
        sys.exit(1)

    from pydantic import SecretStr

    try:
        run_login_flow(
            client_id=client_id,
            client_secret=SecretStr(client_secret),
            token_store=TokenStore(),
            callback_port=args.port,
            open_browser=not args.no_browser,
        )
    except UserError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _run_server(args: argparse.Namespace) -> None:
    """Handle the serve subcommand (default)."""
    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)


def main() -> None:
    """Run the MCP server, or the OAuth login flow."""
    parser = argparse.ArgumentParser(description="MCP server for pCloud")
    subparsers = parser.add_subparsers(dest="command")

    login_parser = subparsers.add_parser(
        "login",
        help="Authorize this app with pCloud via OAuth 2.0",
    )
    login_parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_CALLBACK_PORT,
        help=f"Local callback port (default: {DEFAULT_CALLBACK_PORT})",
    )
    login_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the authorize URL instead of opening a browser",
    )

    serve_parser = subparsers.add_parser("serve", help="Run the MCP server")
    for sub in (parser, serve_parser):
        sub.add_argument(
            "--transport",
            choices=["stdio", "sse", "streamable-http"],
            default="stdio",
            help="Transport protocol (default: stdio)",
        )
        sub.add_argument(
            "--host",
            default="127.0.0.1",
            help="Host to bind to for HTTP transports (default: 127.0.0.1)",
        )
        sub.add_argument(
            "--port",
            type=int,
            default=DEFAULT_PORT,
            help=f"Port to bind to for HTTP transports (default: {DEFAULT_PORT})",
        )

    args = parser.parse_args()

    if args.command == "login":
        _run_login(args)
    else:
        _run_server(args)

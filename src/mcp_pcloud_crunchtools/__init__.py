r"""MCP pCloud CrunchTools - Secure MCP server for pCloud storage.

Usage:
    mcp-pcloud-crunchtools

    python -m mcp_pcloud_crunchtools

    uvx mcp-pcloud-crunchtools

Environment Variables:
    PCLOUD_ACCESS_TOKEN: Required. pCloud OAuth access token.
    PCLOUD_ACCESS_TOKEN_FILE: Preferred alternative -- path to a file
        holding the token. Takes precedence over PCLOUD_ACCESS_TOKEN.
    PCLOUD_API_HOST: Optional. api.pcloud.com (default) or eapi.pcloud.com
        for EU-region accounts.

Example with Claude Code:
    claude mcp add mcp-pcloud-crunchtools \\
        --env PCLOUD_ACCESS_TOKEN=your_token_here \\
        -- uvx mcp-pcloud-crunchtools
"""

import argparse

from .server import mcp

__version__ = "2.0.0"
__all__ = ["main", "mcp"]

DEFAULT_PORT = 8028


def main() -> None:
    """Run the MCP server."""
    parser = argparse.ArgumentParser(description="MCP server for pCloud")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to for HTTP transports (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to bind to for HTTP transports (default: {DEFAULT_PORT})",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)

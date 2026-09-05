# mcp-pcloud-crunchtools

<!-- mcp-name: io.github.crunchtools/pcloud -->

Secure MCP server for [pCloud](https://www.pcloud.com/) cloud storage. Browse, search, read, and manage files and folders in a pCloud account through the Model Context Protocol.

Authentication is OAuth-only. pCloud accounts with two-factor authentication enabled cannot be accessed with a username and password, and password-derived tokens travel in the URL query string — so this server accepts an OAuth access token and sends it in an `Authorization: Bearer` header.

## Installation

```bash
# uvx (zero-install)
uvx mcp-pcloud-crunchtools

# PyPI
pip install mcp-pcloud-crunchtools

# Container
podman run quay.io/crunchtools/mcp-pcloud
```

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `PCLOUD_ACCESS_TOKEN` | yes* | pCloud OAuth access token |
| `PCLOUD_ACCESS_TOKEN_FILE` | yes* | Path to a file holding the token — **preferred**, takes precedence |
| `PCLOUD_API_HOST` | no | `api.pcloud.com` (default) or `eapi.pcloud.com` for EU accounts |

\* Exactly one of the two is required.

Create an access token at [pCloud my_apps](https://docs.pcloud.com/my_apps/). The `_FILE` form is preferred for container deployments — it works with podman secrets, Kubernetes secret volumes, and systemd `LoadCredential=`. The server warns (but does not fail) if the token file is group- or world-readable.

### Claude Code

```bash
claude mcp add mcp-pcloud-crunchtools \
    --env PCLOUD_ACCESS_TOKEN=your_token_here \
    -- uvx mcp-pcloud-crunchtools
```

## Transports

```bash
mcp-pcloud-crunchtools                                    # stdio (default)
mcp-pcloud-crunchtools --transport sse --port 8028
mcp-pcloud-crunchtools --transport streamable-http --port 8028
```

## Tools

**Folders** — `pcloud_list_folder`, `pcloud_create_folder`, `pcloud_delete_folder`, `pcloud_rename_folder`, `pcloud_copy_folder`

**Files** — `pcloud_get_file_info`, `pcloud_delete_file`, `pcloud_rename_file`, `pcloud_copy_file`, `pcloud_read_text_file`, `pcloud_get_checksum`

**Links** — `pcloud_get_file_link`, `pcloud_create_public_link`

**Search & account** — `pcloud_search`, `pcloud_get_user_info`

`pcloud_create_public_link` publishes a file to anyone holding the returned URL, and `pcloud_get_file_link` returns a time-limited direct download URL. Treat both as credential-issuing operations when building tool allowlists.

## Security

- OAuth token held as a Pydantic `SecretStr`, never logged and scrubbed from error messages
- Token sent in an `Authorization` header, never in a URL
- All arguments validated by Pydantic models with `extra="forbid"`; paths must be absolute and may not contain `..` traversal segments
- TLS certificate validation always on, 30s request timeout, 10 MB response ceiling
- No filesystem access, shell execution, or code evaluation

## Development

```bash
uv sync
uv run ruff check src tests
uv run mypy src
uv run pytest -v
gourmand --full .
podman build -f Containerfile .
```

## License

AGPL-3.0-or-later

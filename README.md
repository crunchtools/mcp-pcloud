# mcp-pcloud-crunchtools

<!-- mcp-name: io.github.crunchtools/pcloud -->

Secure MCP server for [pCloud](https://www.pcloud.com/) cloud storage. Browse, search, read, and manage files and folders in a pCloud account through the Model Context Protocol.

Authentication is OAuth 2.0. Register an application, run `mcp-pcloud-crunchtools login` once, and the server manages the bearer token from there. pCloud accounts with two-factor authentication enabled cannot be accessed with a username and password, and password-derived tokens travel in the URL query string. This server never derives a credential from a password and never puts one in a URL — the client secret is only ever sent in a POST body.

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

Register an application at [pCloud my_apps](https://docs.pcloud.com/my_apps/), add `http://localhost:8029/callback` to its redirect URIs, then:

```bash
export PCLOUD_CLIENT_ID=your_client_id
export PCLOUD_CLIENT_SECRET=your_client_secret

mcp-pcloud-crunchtools login
```

`login` opens a browser, you approve the app, and the resulting bearer token is cached at `~/.config/mcp-pcloud/tokens.json` (0600). That is the whole setup. **pCloud access tokens do not expire** — its `oauth2_token` endpoint returns no `refresh_token` and no `expires_in` — so there is no renewal cycle and nothing to rotate on a schedule. The token stays valid until you revoke the app from the pCloud console, which does not touch your account password or any other session.

The login flow also records which data center holds the account, so the region is never configured by hand.

### Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PCLOUD_CLIENT_ID` | preferred | pCloud application client id |
| `PCLOUD_CLIENT_SECRET` | preferred | pCloud application client secret |
| `PCLOUD_ACCESS_TOKEN` | alternative | A bearer token supplied directly, for containers and CI |
| `PCLOUD_AUTH_TOKEN` | last resort | A pCloud desktop-client session token |
| `PCLOUD_TOKEN_STORE_PATH` | no | Where `login` caches the token (default `~/.config/mcp-pcloud/tokens.json`) |
| `PCLOUD_API_HOST` | no | `api.pcloud.com` or `eapi.pcloud.com`; normally discovered during login |

Modes are selected in that order: a client id *and* secret together select OAuth application mode and outrank everything else; otherwise a static access token is used; a session token is the last resort.

Every credential variable also accepts a `_FILE` form (`PCLOUD_CLIENT_SECRET_FILE`, `PCLOUD_ACCESS_TOKEN_FILE`, …) pointing at a file that holds the value. The `_FILE` form takes precedence and is preferred for container deployments — it works with podman secrets, Kubernetes secret volumes, and systemd `LoadCredential=`. The server warns (but does not fail) if the file is group- or world-readable.

### Headless hosts

A container has no browser, and `login` cannot run inside one. Prefer
authorizing over MCP: call `pcloud_auth_start`, open the URL it returns,
approve, and pCloud redirects to the server's own `/callback` route, which
completes the exchange. Nothing is copied by hand and no port is forwarded.
This needs `PCLOUD_OAUTH_REDIRECT_URI` set to a URL that reaches `/callback`
from your browser, and that same URL registered in the pCloud application.

Without a reachable callback URL, `login --manual` authorizes with no listener
at all: pCloud displays the code and you paste it back.

```bash
mcp-pcloud-crunchtools login --manual
```

Failing both, forward the callback port and run `login` over SSH:

```bash
ssh -L 8029:localhost:8029 yourhost
mcp-pcloud-crunchtools login --no-browser    # prints the URL; open it locally
```

Alternatively, run `login` on a workstation and copy the resulting `tokens.json` to the host.

### Which credential do I have?

If you only have the token the pCloud desktop client stores, that is a *session* token, not an OAuth token: pCloud rejects it as an `access_token` with `result 2094`, so set it as `PCLOUD_AUTH_TOKEN`. Prefer an application: a session token *is* the account, carries no scope, and cannot be revoked independently of the client that issued it.

### Claude Code

```bash
claude mcp add mcp-pcloud-crunchtools \
    --env PCLOUD_CLIENT_ID=your_client_id \
    --env PCLOUD_CLIENT_SECRET=your_client_secret \
    -- uvx mcp-pcloud-crunchtools
```

## Transports

```bash
mcp-pcloud-crunchtools login                              # authorize once
mcp-pcloud-crunchtools                                    # stdio (default)
mcp-pcloud-crunchtools serve --transport sse --port 8028
mcp-pcloud-crunchtools serve --transport streamable-http --port 8028
```

## Tools

**Folders** — `pcloud_list_folder`, `pcloud_create_folder`, `pcloud_delete_folder`, `pcloud_rename_folder`, `pcloud_copy_folder`

**Files** — `pcloud_get_file_info`, `pcloud_delete_file`, `pcloud_rename_file`, `pcloud_copy_file`, `pcloud_read_text_file`, `pcloud_get_checksum`

**Links** — `pcloud_get_file_link`, `pcloud_create_public_link`

**Search & account** — `pcloud_search`, `pcloud_get_user_info`

**Authorization** — `pcloud_auth_status`, `pcloud_auth_start`, `pcloud_auth_result`

`pcloud_create_public_link` publishes a file to anyone holding the returned URL, and `pcloud_get_file_link` returns a time-limited direct download URL. Treat both as credential-issuing operations when building tool allowlists.

## Security

- Tokens and the client secret held as Pydantic `SecretStr`, never logged and scrubbed from error messages, including a token loaded from the store rather than the environment
- `state` parameter checked with a constant-time comparison on the OAuth callback; the redirect's `hostname` is validated against the known pCloud regions before it is used
- Token store written 0600 via `os.open`, never through a world-readable temporary file
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

# mcp-pcloud-crunchtools

Secure MCP server for pCloud cloud storage. Python 3.11+, FastMCP, httpx, Pydantic v2.

Governance lives in `.specify/memory/constitution.md`. Read it before changing the security model.

## Architecture

```
src/mcp_pcloud_crunchtools/
├── __init__.py   # CLI (login/serve), transports, version
├── server.py     # @mcp.tool() wrappers -- validation and delegation only
├── client.py     # httpx client, Bearer auth, result-code mapping
├── auth.py       # OAuth 2.0 code flow, token store
├── config.py     # auth mode resolution, credential resolution, region host
├── models.py     # Pydantic input models
├── errors.py     # safe error hierarchy
└── tools/        # pure async functions, one module per category
```

Business logic never goes in `server.py`. MCP registration never goes in `tools/*.py`.

## Authentication

Three modes, resolved in this order by `config.py`:

1. **OAUTH_APP** — `PCLOUD_CLIENT_ID` + `PCLOUD_CLIENT_SECRET`. `mcp-pcloud-crunchtools login` runs the OAuth 2.0 authorization code flow and writes the bearer token to the token store (`~/.config/mcp-pcloud/tokens.json`, 0600, override with `PCLOUD_TOKEN_STORE_PATH`). Both credentials must be present; a client id alone does not select this mode.
2. **STATIC_TOKEN** — `PCLOUD_ACCESS_TOKEN`, a bearer token supplied directly, for containers and CI.
3. **SESSION_TOKEN** — `PCLOUD_AUTH_TOKEN`, sent as an `auth` field in a POST body.

All honor the `_FILE` convention, which takes precedence.

**pCloud issues no refresh tokens.** `oauth2_token` returns only `result`, `access_token`, `token_type` and `uid` — no `refresh_token`, no `expires_in`. There is deliberately no expiry recorded and no refresh cycle; do not add one. A revoked token surfaces as a pCloud result code mapped to `AuthenticationError`, whose message points at `login`.

The login callback carries `hostname`, so the region is discovered rather than configured. Validate it against `VALID_API_HOSTS` before use — a redirect must never be able to aim the client at an arbitrary host.

Username/password authentication was removed in 2.0.0. pCloud returns `result 2297` for accounts with 2FA enabled, and the flow put the token in the URL query string. Do not reintroduce it, and never move a credential into a URL — that is the property Layer 3 defends. The client secret travels in a POST body for the same reason.

A token loaded from the store is not in the environment, so `errors._scrub` cannot find it by variable name. `TokenStore` calls `errors.register_secret()` on load and save. Any future credential that does not arrive via an env var must do the same.

## Tools (15)

Folders: `pcloud_list_folder`, `pcloud_create_folder`, `pcloud_delete_folder`, `pcloud_rename_folder`, `pcloud_copy_folder`

Files: `pcloud_get_file_info`, `pcloud_delete_file`, `pcloud_rename_file`, `pcloud_copy_file`, `pcloud_read_text_file`, `pcloud_get_checksum`

Links: `pcloud_get_file_link`, `pcloud_create_public_link`

Search and account: `pcloud_search`, `pcloud_get_user_info`

## Quality Gates

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -v
podman run --rm -v "$PWD":/src:Z -w /src quay.io/crunchtools/gourmand:latest --full
podman build -f Containerfile .
```

The gourmand container's entrypoint is already `gourmand`, so pass flags only. `--full` takes no path argument.

## Adding a Tool

Update `tools/<category>.py`, `tools/__init__.py`, `server.py`, `tests/test_tools.py`, and the counts in `tests/test_server.py`. Keep the version in sync across `pyproject.toml`, `__init__.py`, `server.json`, and the `Containerfile` label.

## Deployment

Port 8028, streamable-http, containerized on lotor behind the Trentina gateway.

The container is headless, so `login` cannot run inside it. Authorize with the callback port forwarded (`ssh -L 8029:localhost:8029 lotor`) and point `PCLOUD_TOKEN_STORE_PATH` at a mounted path so the token survives `--rm`.

The Trentina gateway deliberately withholds `pcloud_delete_file` and `pcloud_delete_folder`, exposing 13 of the 15 registered tools. That is policy, not an oversight: agents do not delete files in pCloud. Do not "fix" the gap by adding them to the allowlist.

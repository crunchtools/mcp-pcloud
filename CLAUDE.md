# mcp-pcloud-crunchtools

Secure MCP server for pCloud cloud storage. Python 3.11+, FastMCP, httpx, Pydantic v2.

Governance lives in `.specify/memory/constitution.md`. Read it before changing the security model.

## Architecture

```
src/mcp_pcloud_crunchtools/
├── __init__.py   # CLI, transports, version
├── server.py     # @mcp.tool() wrappers -- validation and delegation only
├── client.py     # httpx client, Bearer auth, result-code mapping
├── config.py     # credential resolution, region host
├── models.py     # Pydantic input models
├── errors.py     # safe error hierarchy
└── tools/        # pure async functions, one module per category
```

Business logic never goes in `server.py`. MCP registration never goes in `tools/*.py`.

## Authentication

Token-based, OAuth preferred. `PCLOUD_ACCESS_TOKEN` is sent as an `Authorization: Bearer` header on a GET; `PCLOUD_AUTH_TOKEN` (a pCloud session token) is sent as an `auth` field in a POST body. OAuth wins when both are set. Both honor the `_FILE` convention, which takes precedence.

Username/password authentication was removed in 2.0.0. pCloud returns `result 2297` for accounts with 2FA enabled, and the flow put the token in the URL query string. Do not reintroduce it, and never move a credential into a URL — that is the property Layer 3 defends.

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

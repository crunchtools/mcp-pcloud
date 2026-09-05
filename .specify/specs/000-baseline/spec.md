# Baseline Specification — mcp-pcloud-crunchtools

> **Status:** Implemented
> **Version:** 2.0.0

## Purpose

Expose a pCloud account through the Model Context Protocol so an agent can browse, search, read, and manage files and folders.

## Authentication

OAuth access token only, sent as `Authorization: Bearer`. Supplied via `PCLOUD_ACCESS_TOKEN` or, preferred, `PCLOUD_ACCESS_TOKEN_FILE`.

Username/password digest authentication was removed in 2.0.0 for two reasons: pCloud rejects it outright on accounts with two-factor authentication enabled (`result 2297`), and it placed the resulting session token in the URL query string, violating Layer 3 of the security model.

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `PCLOUD_ACCESS_TOKEN` | one of | — | OAuth access token |
| `PCLOUD_ACCESS_TOKEN_FILE` | one of | — | Path to token file; takes precedence |
| `PCLOUD_API_HOST` | no | `api.pcloud.com` | `api.pcloud.com` or `eapi.pcloud.com` |

## Tool Inventory (15)

| Tool | Module | pCloud method | Mutates |
|------|--------|---------------|---------|
| `pcloud_list_folder` | tools/folders.py | `listfolder` | no |
| `pcloud_create_folder` | tools/folders.py | `createfolderifnotexists` | yes |
| `pcloud_delete_folder` | tools/folders.py | `deletefolder` / `deletefolderrecursive` | yes |
| `pcloud_rename_folder` | tools/folders.py | `renamefolder` | yes |
| `pcloud_copy_folder` | tools/folders.py | `copyfolder` | yes |
| `pcloud_get_file_info` | tools/files.py | `stat` | no |
| `pcloud_delete_file` | tools/files.py | `deletefile` | yes |
| `pcloud_rename_file` | tools/files.py | `renamefile` | yes |
| `pcloud_copy_file` | tools/files.py | `copyfile` | yes |
| `pcloud_read_text_file` | tools/files.py | `gettextfile` | no |
| `pcloud_get_checksum` | tools/files.py | `checksumfile` | no |
| `pcloud_get_file_link` | tools/links.py | `getfilelink` | no |
| `pcloud_create_public_link` | tools/links.py | `getfilepublink` | yes |
| `pcloud_search` | tools/search.py | `search` | no |
| `pcloud_get_user_info` | tools/account.py | `userinfo` | no |

`pcloud_get_file_link` returns a time-limited direct download URL and `pcloud_create_public_link` mints a durable public URL. Both hand out access to file content without further authentication, so gateway allowlists MUST treat them as privileged even though only one mutates state.

## Error Hierarchy

`UserError` is the base. `ConfigurationError`, `PCloudApiError`, `AuthenticationError`, `TwoFactorRequiredError`, `PathNotFoundError`, `PermissionDeniedError`, `RateLimitError`, and `ValidationError` derive from it.

pCloud result codes map as: 1000/2000 to `AuthenticationError`, 2297 to `TwoFactorRequiredError`, 2005/2009 to `PathNotFoundError`, 2003 to `PermissionDeniedError`, 4000 to `RateLimitError`, anything else to `PCloudApiError`.

## Modules

| Module | Responsibility |
|--------|----------------|
| `__init__.py` | CLI argument parsing, transport selection, version |
| `server.py` | `@mcp.tool()` registration and argument validation |
| `client.py` | httpx client, auth header, timeouts, size limits, result-code mapping |
| `config.py` | Credential resolution (`_FILE` precedence), region host validation |
| `models.py` | Pydantic input models |
| `errors.py` | Safe error hierarchy, credential scrubbing, identifier truncation |
| `tools/` | Pure async functions, one module per category |

## Deployment

Port 8028, streamable-http, behind the Trentina gateway on lotor as `mcp-pcloud.crunchtools.com.service`.

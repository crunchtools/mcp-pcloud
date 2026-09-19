# Baseline Specification — mcp-pcloud-crunchtools

> **Status:** Implemented
> **Version:** 2.2.0

## Purpose

Expose a pCloud account through the Model Context Protocol so an agent can browse, search, read, and manage files and folders.

## Authentication

OAuth 2.0. Three modes, resolved in descending preference.

| Mode | Variables | Transport |
|------|-----------|-----------|
| `OAUTH_APP` | `PCLOUD_CLIENT_ID` + `PCLOUD_CLIENT_SECRET` | `Authorization: Bearer` header, GET; token from the store |
| `STATIC_TOKEN` | `PCLOUD_ACCESS_TOKEN` | `Authorization: Bearer` header, GET |
| `SESSION_TOKEN` | `PCLOUD_AUTH_TOKEN` | `auth` field in a POST body |

All accept a `_FILE` form which takes precedence. `OAUTH_APP` requires both the client id and the secret; a client id alone does not select it, so a half-configured application cannot silently shadow a working token.

`OAUTH_APP` was added in 2.2.0 and is the intended path. `mcp-pcloud-crunchtools login` runs the authorization code flow: a localhost HTTP server receives pCloud's redirect, the `state` parameter is compared in constant time, and the code is exchanged for a bearer token over POST so the client secret never enters a URL. The token is written to `~/.config/mcp-pcloud/tokens.json` at 0600 via `os.open`.

**pCloud issues no refresh tokens.** `oauth2_token` returns `result`, `access_token`, `token_type` and `uid` only. There is no `expires_in` and therefore no expiry recorded and no refresh cycle. `TokenData` deliberately has no `expires_at` field: fabricating one would expire a credential that is still valid. Revocation is the only thing that ends a token's life, and it surfaces as a pCloud result code mapped to `AuthenticationError`.

The authorize redirect carries `hostname` and `locationid` identifying the account's data center. That hostname is validated against the known region endpoints and then persisted with the token, so the region is discovered rather than configured. An unrecognized hostname is discarded in favor of the US endpoint -- a redirect must not be able to aim the client at an arbitrary host.

A token read from the store never appears in the environment, so `errors._scrub` cannot locate it by variable name. `TokenStore` registers it through `errors.register_secret()` on both load and save, preserving the property that no credential reaches a user-facing error message.

Username/password digest authentication was removed in 2.0.0 for two reasons: pCloud rejects it outright on accounts with two-factor authentication enabled (`result 2297`), and it placed the resulting token in the URL query string, violating Layer 3.

Session-token support was added in 2.1.0 as a stopgap for accounts with no provisioned OAuth application. With `OAUTH_APP` available that rationale no longer holds, but the mode is retained for accounts that still have only a desktop-client token. It remains the least preferred: a session token is the account, carries no scope, and cannot be revoked independently of the client that issued it.

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `PCLOUD_CLIENT_ID` | preferred | -- | pCloud application client id |
| `PCLOUD_CLIENT_SECRET` | preferred | -- | pCloud application client secret |
| `PCLOUD_ACCESS_TOKEN` | alternative | -- | Bearer token supplied directly |
| `PCLOUD_AUTH_TOKEN` | last resort | -- | pCloud session token |
| `*_FILE` | no | -- | File form of any credential; takes precedence |
| `PCLOUD_TOKEN_STORE_PATH` | no | `~/.config/mcp-pcloud/tokens.json` | Where `login` caches the token |
| `PCLOUD_API_HOST` | no | discovered, else `api.pcloud.com` | `api.pcloud.com` or `eapi.pcloud.com`; an explicit value overrides the stored region |

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

`UserError` is the base. `ConfigurationError`, `PCloudApiError`, `AuthenticationError`, `TokenUnavailableError`, `TwoFactorRequiredError`, `PathNotFoundError`, `PermissionDeniedError`, `RateLimitError`, and `ValidationError` derive from it.

`TokenUnavailableError` means OAuth application mode is configured but `login` has not been run. It is distinct from `AuthenticationError`, which means a credential existed and pCloud rejected it -- the two call for different fixes.

pCloud result codes map as: 1000/2000 to `AuthenticationError`, 2297 to `TwoFactorRequiredError`, 2005/2009 to `PathNotFoundError`, 2003 to `PermissionDeniedError`, 4000 to `RateLimitError`, anything else to `PCloudApiError`.

## Modules

| Module | Responsibility |
|--------|----------------|
| `__init__.py` | CLI subcommands (`login`, `serve`), transport selection, version |
| `auth.py` | OAuth 2.0 authorization code flow, token store |
| `server.py` | `@mcp.tool()` registration and argument validation |
| `client.py` | httpx client, auth header, timeouts, size limits, result-code mapping |
| `config.py` | Auth mode selection, credential resolution (`_FILE` precedence), region host validation |
| `models.py` | Pydantic input models |
| `errors.py` | Safe error hierarchy, credential scrubbing, identifier truncation |
| `tools/` | Pure async functions, one module per category |

## Deployment

Port 8028, streamable-http, behind the Trentina gateway on lotor as `mcp-pcloud.crunchtools.com.service`.

The container is headless and runs `--rm`, so `login` cannot run inside it and a token written to the default path would not survive a restart. Authorize with the callback port forwarded and set `PCLOUD_TOKEN_STORE_PATH` to a mounted path.

The gateway exposes 13 of the 15 registered tools. `pcloud_delete_file` and `pcloud_delete_folder` are withheld by policy: agents do not delete files in this account. This is a deliberate omission, not a configuration gap.

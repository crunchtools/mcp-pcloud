# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.3.0] - 2026-09-19

### Security
- Upgraded FastMCP from 2.14.7 to 4.x, which resolves two advisories that had
  no fix available inside the previous `>=2.0,<3.0` pin (2.14.7 was already the
  newest 2.x). Both are patched in FastMCP 3.2.0:
  - **CVE-2026-32871** (critical) — SSRF and path traversal in the OpenAPI provider
  - **CVE-2026-27124** (high) — missing consent verification in the OAuth proxy callback

  Neither was reachable from this server, which uses plain `FastMCP()` with
  `@mcp.tool()` and neither the OpenAPI provider nor the OAuth proxy. The
  upgrade removes the vulnerable code from the image regardless.

### Changed
- Dependency pin moved from `fastmcp>=2.0,<3.0` to `fastmcp>=4.0,<5.0`.
- Tests updated for the FastMCP 4 API: `get_tools()`, which returned a dict,
  was replaced by `list_tools()`, which returns a sequence of `Tool` objects.
  Only tests called it -- `server.py` does not, so the server itself needed no
  change.

No change to the tool surface, environment variables, or CLI: the same 15
tools, the same configuration, the same commands.

## [2.2.0] - 2026-09-19

### Added
- OAuth 2.0 authorization code flow. `PCLOUD_CLIENT_ID` + `PCLOUD_CLIENT_SECRET`
  select an application, and `mcp-pcloud-crunchtools login` obtains the bearer
  token: localhost callback, constant-time `state` check, code exchanged over
  POST so the client secret never enters a URL.
- Token store at `~/.config/mcp-pcloud/tokens.json`, written 0600, overridable
  with `PCLOUD_TOKEN_STORE_PATH`.
- Region auto-discovery. The authorize redirect reports the account's data
  center; the hostname is validated against the known endpoints and persisted
  with the token, so `PCLOUD_API_HOST` no longer has to be set by hand.
- `TokenUnavailableError`, distinguishing "login has not been run" from
  "pCloud rejected the credential".
- `errors.register_secret()`, so a token loaded from the store is scrubbed from
  error messages even though it never appears in the environment.

### Changed
- `serve` is now an explicit subcommand; running with no subcommand still
  serves, so existing invocations are unaffected.
- Authentication modes are ranked: an OAuth application outranks a static
  access token, which outranks a session token. Both older modes are retained.
- Aligned the pre-commit `ruff` pin with the version the project actually
  builds against; the two had drifted far enough to disagree on lint results.

## [2.1.0] - 2026-09-05

This changelog starts here (RT #1484). The entry below was reconstructed from the
`v2.0.0...v2.1.0` commit range in RT #1485, which released this version.

### Added
- **pCloud session tokens are accepted as a credential** via `PCLOUD_AUTH_TOKEN`
  (and `PCLOUD_AUTH_TOKEN_FILE`), alongside the existing OAuth variables. OAuth
  still wins whenever both are configured.

  pCloud issues session tokens to its own desktop client and rejects them as an
  `access_token` (result 2094), so they cannot be exchanged for OAuth tokens. An
  account with no provisioned OAuth application therefore had no usable credential
  at all.

  The session token is sent as an `auth` field in a POST body, never in a query
  string, preserving the property the no-credentials-in-URL rule actually defends:
  a credential must not land in access logs, proxies or referrers.
  Password-derived authentication remains removed.

### Fixed
- pCloud result 2094 now maps onto `AuthenticationError` rather than surfacing raw.

### Changed
- Repo constitution amended to 1.1.0: Section I.3 widened from "OAuth only" to
  "token-based, OAuth preferred".

## [2.0.0] - 2026-09-05

Tagged the same day as 2.1.0. No release notes recorded.

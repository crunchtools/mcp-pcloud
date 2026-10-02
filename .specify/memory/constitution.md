# mcp-pcloud-crunchtools Constitution

> **Version:** 1.2.0
> **Ratified:** 2026-09-05
> **Amended:** 2026-10-02
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.18.0
> **Profile:** MCP Server

This file holds what is specific to mcp-pcloud. The fleet rules and the MCP
Server profile (five-layer security model, two-layer tools, distribution
channels, transport modes, quality gates, Gourmand) apply at the inherited
version and are checked against this repo's files by `constitution.yml`. They
are not restated here.

## Security Model Specifics

- **Credentials:** held as Pydantic `SecretStr`, never logged, rendered as
  `***` by `Config.__repr__`/`__str__`, and removed from every outgoing error
  message by `errors._scrub`. Each credential variable honors the `_FILE`
  convention; the file wins over the plain variable, contents are stripped on
  read, and a token file readable beyond its owner raises a warning, never a
  failure.
- **Input limits:** paths MUST be absolute, free of NUL bytes,
  length-bounded, and free of `..` segments. Traversal rejection is what keeps
  a caller from escaping a folder it was scoped to by a gateway tool
  allowlist. Search queries are length-bounded and non-empty.
- **API:** requests time out after 30s; responses above 10 MB are rejected;
  TLS validation stays at httpx defaults and MUST NOT be made configurable
  off. pCloud result codes are mapped onto the safe error hierarchy, not
  surfaced raw.
- **Surface:** pure pCloud API wrappers. No local filesystem access beyond
  reading the credential file.

## Authentication Principle

Token-based, OAuth preferred. This server never derives a credential from a
password and never places one in a URL, where it would leak into access logs,
proxies and referrers. pCloud's legacy digest login put the token in the
query string and cannot complete on accounts with two-factor authentication;
username/password mode was removed in 2.0.0 and MUST NOT return.

| Kind | Variable | Transport |
|------|----------|-----------|
| OAuth access token | `PCLOUD_ACCESS_TOKEN` | `Authorization: Bearer` header, GET |
| pCloud session token | `PCLOUD_AUTH_TOKEN` | `auth` field in a POST body |

When both are configured the OAuth token wins. The session token is a
fallback for accounts with no OAuth application provisioned: pCloud issues it
to its own desktop client and rejects it as an `access_token` (`result
2094`), so it cannot be exchanged for an OAuth token. It carries the same
authority and is protected identically.

Reintroducing username/password authentication, or moving any credential
into a URL or query string, requires an amendment to this file.

## Dependency Pins

`fastmcp` is pinned `>=2.0,<3.0` deliberately: fastmcp 3.x pulls `mcp>=2.0`,
which renames `FastMCP` to `MCPServer` and changes the client stream
contract, and the backend fleet runs the v1 protocol.

## Instance

| Context | Name |
|---------|------|
| GitHub repo | `crunchtools/mcp-pcloud` |
| PyPI package | `mcp-pcloud-crunchtools` |
| Python module | `mcp_pcloud_crunchtools` |
| Container image | `quay.io/crunchtools/mcp-pcloud`, `ghcr.io/crunchtools/mcp-pcloud` |
| MCP Registry | `io.github.crunchtools/pcloud` |
| systemd service | `mcp-pcloud.crunchtools.com.service` |
| HTTP port | 8028 |

The version MUST be identical in `pyproject.toml`, `__init__.py`,
`server.py`, `server.json` and the `Containerfile` label.

## Test Invariants

Error-code mapping, token scrubbing and identifier truncation each keep
explicit tests. `EXPECTED_TOOL_COUNT` and `EXPECTED_TOOLS` in
`tests/test_server.py` change with every tool added or removed.

## History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-09-05 | Initial ratification alongside the 2.0.0 Python rewrite |
| 1.1.0 | 2026-09-05 | Authentication widened from "OAuth only" to "token-based, OAuth preferred", admitting pCloud session tokens in a POST body; no-credentials-in-URL rule unchanged |
| 1.2.0 | 2026-10-02 | Manifest under constitution v1.18.0: profile restatement removed, mcp-pcloud specifics kept |

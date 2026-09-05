# mcp-pcloud-crunchtools Constitution

> **Version:** 1.0.0
> **Ratified:** 2026-09-05
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.10.0
> **Profile:** MCP Server

This constitution establishes the core principles, constraints, and workflows that govern all development on mcp-pcloud-crunchtools.

---

## I. Core Principles

### 1. Five-Layer Security Model

Every change MUST preserve all five security layers. No exceptions.

**Layer 1 — Credential Protection:**
- The pCloud OAuth access token is held as a Pydantic `SecretStr` and is never logged.
- `PCLOUD_ACCESS_TOKEN_FILE` is supported and takes precedence over `PCLOUD_ACCESS_TOKEN`. File contents are stripped on read; a token file readable beyond its owner raises a warning, never a failure.
- `Config.__repr__` and `Config.__str__` render the token as `***`.
- `errors._scrub` removes any configured credential value from every outgoing error message.

**Layer 2 — Input Validation:**
- Every tool validates input through a Pydantic v2 model with `extra="forbid"`.
- Paths MUST be absolute, free of NUL bytes, length-bounded, and free of `..` traversal segments. Traversal rejection is what keeps a caller from escaping a folder they were scoped to by a gateway tool allowlist.
- Search queries are length-bounded and non-empty.

**Layer 3 — API Hardening:**
- The access token is sent in an `Authorization: Bearer` header and MUST NOT appear in a URL. Password-derived tokens travelled in the query string; that authentication mode was removed in 2.0.0 and MUST NOT return.
- TLS certificate validation is left at httpx defaults and MUST NOT be made configurable off.
- Requests carry a 30 second timeout; responses above 10 MB are rejected.
- pCloud result codes are mapped onto the safe error hierarchy rather than surfaced raw.

**Layer 4 — Dangerous Operation Prevention:**
- No shell execution, no code evaluation, no `eval()`/`exec()`, no local filesystem access beyond reading the credential file.
- Tools are pure pCloud API wrappers.

**Layer 5 — Supply Chain Security:**
- Weekly automated CVE scanning via GitHub Actions.
- Hummingbird FIPS container base images, distroless runtime.
- Gourmand AI slop detection gates every PR at zero violations.

### 2. Two-Layer Tool Architecture

- `server.py` holds `@mcp.tool()` wrappers that validate arguments and delegate.
- `tools/*.py` holds pure async functions that call `client.py`.

Business logic MUST NOT live in `server.py`. MCP registration MUST NOT live in `tools/*.py`.

### 3. Authentication Is OAuth Only

pCloud accounts with two-factor authentication enabled cannot complete the legacy digest login, and that flow placed the session token in the URL. This server accepts an OAuth access token only. Reintroducing username/password authentication requires a constitutional amendment.

### 4. Three Distribution Channels

Every release ships through uvx, pip (PyPI), and container (Quay.io + GHCR) simultaneously.

### 5. Three Transport Modes

stdio (default), SSE, and streamable-http MUST all remain supported.

---

## II. Technology Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| MCP Framework | FastMCP (`fastmcp>=2.0,<3.0`) |
| HTTP Client | httpx |
| Validation | Pydantic v2 |
| Container Base | Hummingbird FIPS |
| Package Manager | uv |
| Build System | hatchling |
| Linter | ruff |
| Type Checker | mypy (strict) |
| Tests | pytest + pytest-asyncio |
| Slop Detector | gourmand |

`fastmcp` is pinned below 3.0 deliberately: fastmcp 3.x pulls `mcp>=2.0`, which renames `FastMCP` to `MCPServer` and changes the client stream contract. The lotor backend fleet runs the v1 protocol.

---

## III. Container Conventions

- Build file is `Containerfile`.
- Multi-stage venv build; builder and runtime MUST both be Hummingbird FIPS images.
- Runtime is distroless — no shell-form `RUN` in the runtime stage.
- Required labels: `name`, `version`, `summary`, `maintainer`, plus `org.opencontainers.image.source`, `.description`, and `.licenses`.
- `EXPOSE 8028` — the assigned HTTP port for this server.

---

## IV. Testing Standards

- Every tool has a mocked test; no live pCloud calls in CI and no token required.
- `httpx.AsyncClient.get` is patched; tool functions are called directly rather than through the MCP wrapper.
- An autouse fixture resets the `config` and `client` singletons between every test.
- `test_tool_count` MUST be updated whenever tools are added or removed.
- Error-code mapping, token scrubbing, and identifier truncation MUST each retain explicit tests.

---

## V. Code Quality Gates

| Gate | Command |
|------|---------|
| Lint | `uv run ruff check src tests` |
| Type Check | `uv run mypy src` |
| Tests | `uv run pytest -v` |
| Gourmand | `gourmand --full` (zero violations) |
| Code Review | Gatehouse AI code review on every PR |
| Container Build | `podman build -f Containerfile .` |

### Gourmand Exception Policy

Exceptions MUST carry a documented justification in `gourmand-exceptions.toml`. Acceptable reasons are standard API patterns, test-specific patterns, and framework requirements. Unacceptable reasons are "the code is special", "the threshold is too strict", and rewording to evade detection. This repository currently declares no exceptions and MUST stay at zero violations without them.

---

## VI. Naming

| Context | Value |
|---------|-------|
| GitHub repo | `crunchtools/mcp-pcloud` |
| PyPI package | `mcp-pcloud-crunchtools` |
| Python module | `mcp_pcloud_crunchtools` |
| Container | `quay.io/crunchtools/mcp-pcloud`, `ghcr.io/crunchtools/mcp-pcloud` |
| MCP Registry | `io.github.crunchtools/pcloud` |
| systemd service | `mcp-pcloud.crunchtools.com.service` |
| License | AGPL-3.0-or-later |

---

## VII. Semantic Versioning

Releases follow Semantic Versioning 2.0.0. MAJOR for incompatible changes to tool signatures or authentication, MINOR for backwards-compatible tools or capabilities, PATCH for backwards-compatible fixes. Version 2.0.0 records the removal of username/password authentication and the port from TypeScript to Python.

The version MUST be identical in `pyproject.toml`, `__init__.py`, `server.py`, `server.json`, and the `Containerfile` label.

---

## VIII. Development Workflow

### Adding a Tool

1. Add the async function to the appropriate `tools/*.py`.
2. Export it from `tools/__init__.py`.
3. Register an `@mcp.tool()` wrapper in `server.py` that validates through a Pydantic model.
4. Add a mocked test in `tests/test_tools.py`.
5. Update `EXPECTED_TOOL_COUNT` and `EXPECTED_TOOLS` in `tests/test_server.py`.
6. Run all quality gates.

### Deprecation Policy

A removed or renamed tool is announced in the release notes of one MINOR release before removal, and removal lands in the next MAJOR.

---

## IX. Governance

This repository carries the full text of its governance. The `Inherits` header declares alignment with the MCP Server profile, not a runtime dependency on it.

Files:
- `.specify/memory/constitution.md` — this document
- `.specify/specs/000-baseline/spec.md` — tool inventory and architecture baseline
- `.specify/templates/` — `plan-template.md` and `spec-template.md`

### Specification-Driven Development

New tool groups, new subsystems, changes to the security model, and changes spanning multiple modules each require a numbered spec under `.specify/specs/` before implementation. Bug fixes, dependency updates, CI changes, documentation, and single-tool additions following Section VIII are exempt.

---

## X. Amendment Process

Amendments follow the universal constitution's process. Changes to the five-layer security model or to the OAuth-only authentication principle require an explicit version bump of this document and a recorded justification.

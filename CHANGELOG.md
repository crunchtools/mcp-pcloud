# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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

# Security boundaries

TenantLens v0.1 is a local workstation tool for APIs you are authorized to test.
The panel is designed for a trusted local operator and binds only to
`127.0.0.1`. It is not a multiuser production server.

## Credentials and retained data

- Project definitions store `TENANTLENS_…` environment references, not token fields.
- Tokens are captured from the server environment at run start and live in memory.
- Credentials are sent only as a Bearer header to the configured target origin.
- Known token values and URL-encoded variants are masked in engine snapshots;
  current `TENANTLENS_` credential environment values are also masked in API
  output and before API project persistence. Browser-test port/path/argument
  control variables are excluded from that environment-wide mask.
- Proof fields whose JSON Pointer resembles token/password/secret/key/auth/cookie
  are masked. Unknown secrets in arbitrary user-supplied text cannot be recognized
  automatically; keep credentials out of names, paths, queries and assertions.
- Raw response bodies, response headers, Authorization headers and cookies are
  not saved. Only configured scalar proof fields (up to 1024 characters each),
  statuses, fixed reason codes and run metadata are retained.
- Scalar proof and project data can still contain private resource identifiers
  or other selected application data. Review exports before sharing.
- SQLite files and CLI reports are created with owner-only permissions on Unix.
  Existing parent directory permissions and Windows ACLs are controlled by the
  operator. The database is not encrypted and has no automatic history expiry.

## Request controls

- Only GET is accepted by the schema. Some applications assign side effects to
  GET; select appropriate endpoints for the API under test.
- Every request checks normalized scheme/host/port against explicit origins.
  v0.1 resolves every relative endpoint against one `base_url` origin.
- HTTP redirects are returned as inconclusive and never followed.
- HTTPS uses Python's default certificate verification and trust store. There
  is no insecure-TLS option.
- Environment proxies are ignored. Each request has a fresh connection and
  header set, with no shared cookies, redirects, retries or token refresh.
- A run is sequential and all request starts share the configured rate limit.
- Socket operations have configured timeouts and response reading also checks a
  monotonic deadline. DNS resolution follows OS behavior; a slow DNS resolver
  can exceed the configured socket timeout. The value is not a hard whole-run
  wall-clock budget. Cancellation takes effect between requests, after an active
  request returns or times out.
- Response bodies are capped at the configured limit, read with at most one
  overflow byte. Compressed responses are not decoded. Invalid/non-JSON data
  cannot satisfy JSON success assertions.
- Scope is an origin boundary, not IP pinning; DNS may change where that origin
  resolves. Internal targets are supported intentionally through explicit config.

## Browser and local server

Host must match `127.0.0.1:port` or `localhost:port`. Origin, when present, must
match that Host. Cross-site Fetch Metadata is rejected. Mutations need the
CSRF header, and JSON bodies are limited to 1 MiB. There is no token submission
endpoint. Static file resolution rejects traversal outside the compiled asset
directory.

The panel uses a same-origin CSP, no remote fonts, no CDN assets and no analytics.
React renders untrusted strings as text. HTML reports escape all dynamic data
and contain no scripts; they are served as downloads with a restrictive CSP.

A malicious process with access to the local machine can reach loopback, read
the operator's environment or obtain the CSRF token. These controls do not
replace OS account isolation. Do not reverse proxy or publish the panel without
designing authentication, transport protection and deployment controls.

## Reporting an issue

For a public reproduction, use the bundled local fixtures and synthetic tokens.
Do not attach real credentials or private reports. If the eventual GitHub
repository enables private vulnerability reporting, use that channel for
security-sensitive details. This ZIP does not create or publish a repository.

# Release validation · v0.1.0

Validated on 2026-10-07 in Linux x86_64 with Python 3.12.14, Node 24.19.0,
and headless Chromium 153.0.8010.0. Windows, macOS and CachyOS were not directly
tested. The source is designed for Python 3.11+; the included CI matrix has not
yet run on a published repository.

## Python checks

`python3 -S -m unittest discover -s tests -v` passes **66 tests**, including:

- Actual HTTP cross-tenant vulnerable/fixed/expired fixtures.
- Incorrect identity and nonexistent-resource baseline handling.
- JSON proof, explicit 2xx denial proof and conflicting proof.
- Session 401, redirect, server error, timeout and response-size behavior.
- Fresh credentials/cookies per account, ignored proxy environment and scope.
- Rejection of an untrusted self-signed TLS certificate.
- Shared rate limit across identity, baseline and matrix request starts.
- CSRF, Host/Origin/Fetch Metadata and static traversal boundaries.
- API project creation/update/delete, background run and report downloads.
- Token redaction in target evidence, API responses and persisted project data.
- Immutable snapshots, preserved history and restart interruption handling.
- Escaped HTML and JSON report roundtripping.

The TLS fixture needs `openssl` to generate its certificate; that single test
is explicitly skipped when `openssl` is unavailable. No Python dependencies
are required for any other test or for the application itself. `-S` disables
Python site package loading for verification.

## Browser checks

`npm run test:browser` passes **23 checks** against a temporary panel and real
local HTTP demo targets:

1. Three demo projects are available.
2. No results are fabricated before execution.
3. Vulnerable fixture yields the expected nine verdicts.
4. Cross-tenant resource proof is visible.
5. Three actionable violations appear in findings.
6. JSON report downloads without credential values.
7. HTML report downloads without credential values.
8. Fixed fixture yields nine PASS results.
9. Expired fixture yields four PASS and five INCONCLUSIVE results.
10. Expired identity appears in the accounts view.
11. Historical snapshots are displayed read-only.
12. Invalid baseline permission is blocked by validation.
13. Saved project survives a page reload.
14. Adding an account expands the matrix.
15. Resource editor validates and adds a row.
16. Project export contains environment references.
17. Deleting a project preserves historical runs.
18. JSON import opens a validated draft.
19. Theme selection persists.
20. The 390-pixel viewport has no document-level horizontal overflow.
21. An active run can be cancelled.
22. Panel requests remain on the panel origin; no external page requests.
23. No browser exceptions or CSP failures occur.

The intentional invalid-baseline test produces one expected HTTP 400 browser
console message. Screenshots in `docs/screenshots` come from these runs.

## Expected demonstration results

| Fixture | PASS | VIOLATION | INCONCLUSIVE | ERROR | Requests |
| --- | ---: | ---: | ---: | ---: | ---: |
| vulnerable | 6 | 3 | 0 | 0 | 15 |
| fixed | 9 | 0 | 0 | 0 | 15 |
| expired | 4 | 0 | 5 | 0 | 9 |

Request counts include identity checks and allowed baselines in addition to the
nine matrix controls. The engine does not send dependent target requests when
identity or baseline verification failed.

## Frontend and release checks

TypeScript validation and the Vite production build pass. Lucide's React Server
Components `use client` directives produce a bundler notice; this application
uses client-side React and was verified in the browser.

The ZIP excludes runtime state, real reports, caches, `node_modules`, environment
files and credentials. It contains compiled panel assets as well as source,
lockfile, fixtures, examples, tests and documentation. The release manifest lists
SHA-256 hashes for included source/artifact files.

Clean-extraction verification runs the Python tests and all three CLI demo
profiles using `python3 -S`, without installing dependencies. This validates
release startup and verdict behavior; it is not a general certification of any
API or a substitute for reviewing the policy and proof assertions.

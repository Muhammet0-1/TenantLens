# TenantLens

[![Checks](https://github.com/Muhammet0-1/TenantLens/actions/workflows/ci.yml/badge.svg)](https://github.com/Muhammet0-1/TenantLens/actions/workflows/ci.yml)

**Evidence-based API authorization tests, with a local web workspace.**

TenantLens compares an explicit access policy against real API responses across
accounts, roles and tenants. It checks account identity and an allowed resource
baseline before evaluating each matrix cell. A `200 OK` alone cannot establish
that a forbidden account accessed the expected resource.

[Türkçe kullanım rehberi](KULLANIM.md) · [Architecture](docs/architecture.md) ·
[Security boundaries](SECURITY.md) · [Validation results](docs/validation.md)

![TenantLens inspecting a cross-tenant access violation](docs/screenshots/matrix-dark.png)

## Run the included release

Requires **Python 3.11+** and a modern browser. The release includes the compiled
React panel. Running it requires **no pip install, npm install or package download**.

Clone this repository (or extract the release ZIP), then run from its directory:

```sh
git clone https://github.com/Muhammet0-1/TenantLens.git
cd TenantLens
python3 -m tenantlens serve --demo
```

Open **http://127.0.0.1:8765**. Select a demo project and click **Testi çalıştır**.
Stop the server with `Ctrl+C`. On Windows, use `py -3` in place of `python3`.

| Local demo | PASS | VIOLATION | INCONCLUSIVE | ERROR | HTTP requests |
| --- | ---: | ---: | ---: | ---: | ---: |
| Data leakage / vulnerable | 6 | 3 | 0 | 0 | 15 |
| Fixed authorization | 9 | 0 | 0 | 0 | 15 |
| Expired Bora session | 4 | 0 | 5 | 0 | 9 |

Three actual loopback API servers run on 8766–8768. Demo credentials are public,
dummy values supplied by `--demo`. Every result is produced by the same engine
used for custom projects.

## Workspace features

- Editable account × resource permission matrix with explicit allow/deny rules.
- Account identity assertions and resource baselines using JSON Pointers.
- Scalar proof fields, decision reasons and observed HTTP statuses per cell.
- Project creation, validated JSON import/export and account/resource editing.
- Background execution, progress and cancellation; one active run per workspace.
- SQLite persistence and immutable completed run snapshots.
- Standalone escaped HTML and structured JSON reports.
- Dark/light themes and a responsive Turkish interface.
- CLI sharing the engine, fixtures and report generator with the panel.

## What each verdict means

| Verdict | Meaning |
| --- | --- |
| `PASS` | The configured access expectation was met with the required verification. |
| `VIOLATION` | Forbidden access matched resource proof, or expected allowed access was explicitly denied. |
| `INCONCLUSIVE` | Identity, baseline, session or evidence could not establish the access outcome. |
| `ERROR` | A request failed, timed out, exceeded the response limit or received a server error. |

An expected allowed request returning a configured denial is a **policy mismatch**;
it does not by itself demonstrate an exploitable vulnerability. Review the reason
code. A `PASS` applies to the specified control at the time of the run.

## Use your own API

1. Copy `examples/custom-project.json`, or create a project in the panel.
2. Set the exact target origin, account identities and resource proof assertions.
3. Assign one allowed baseline account to each resource and define all permissions.
4. Set Bearer tokens in the server process environment using each `auth_env` name.
5. Start the panel without `--demo`, import the JSON and run it.

For **fish**, matching the example:

```fish
read --silent --prompt-str 'User A token: ' token_a
set -gx TENANTLENS_USER_A_TOKEN $token_a
set -e token_a
read --silent --prompt-str 'User B token: ' token_b
set -gx TENANTLENS_USER_B_TOKEN $token_b
set -e token_b
python3 -m tenantlens serve
```

Tokens are read when a run starts. Restart the server after changing the token
environment in another terminal. The UI displays environment references and
availability; it has no token-value input or token-value API.

For Bash, use `read -r -s` followed by `export` for the same variable names.
Bearer is the only authentication adapter in v0.1; custom headers, cookies,
OAuth refresh and multipart/body requests are outside this version's scope.

## CLI

```sh
python3 -m tenantlens check --demo fixed --output reports
python3 -m tenantlens check --demo vulnerable --format json --output reports
python3 -m tenantlens check examples/custom-project.json --output reports
```

Exit codes: `0` expectations met; `1` policy violations; `2` inconclusive checks,
request errors or startup/configuration failure. CLI demo targets use temporary
ports and shut down after the run.

## Scope and limits

v0.1 supports **GET requests to one configured origin, Bearer authentication,
JSON scalar equality assertions and sequential execution**. Limits: 12 accounts,
50 resources, 300 matrix checks, 1–50 requests/second, 0.1–30 second socket timeout,
and 1 KiB–1 MiB response bodies. The default limits are 12 requests/second,
3 seconds in demos (5 for unspecified custom settings), and 256 KiB.

Requests use fresh connections, verified HTTPS certificates, no environment
proxies, no shared cookies, no retries and no followed redirects. The panel binds
only to `127.0.0.1` with Host, Origin and CSRF checks. It is a workstation tool;
remote hosting or shared production service operation needs a separate design.
See [SECURITY.md](SECURITY.md) for exact boundaries and storage behavior.

## Tests and development

Python tests use only the standard library:

```sh
python3 -S -m unittest discover -s tests -v
```

To rebuild the frontend, install Node 22.12+ (or Node 24), then:

```sh
cd web
npm ci
npm run build
npx playwright install chromium
npm run test:browser
```

Package/network access is needed only for this optional development workflow.
The checked-in `tenantlens/static` build keeps release startup offline. The
browser smoke test starts its own temporary panel and real local targets, tests
editing/export/history/cancellation, and generates demo screenshots.

GitHub Actions configuration is included for Python 3.11–3.13 and the frontend
build/browser checks. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Repository map

| Path | Purpose |
| --- | --- |
| `tenantlens/models.py` | Schema validation and JSON Pointer proof |
| `tenantlens/engine.py` | Identity → baseline → matrix decisions |
| `tenantlens/transport.py` | Bounded, scoped HTTP transport |
| `tenantlens/server.py` | Local API and run coordinator |
| `tenantlens/storage.py` | Projects and run snapshot persistence |
| `tenantlens/demo.py` | Vulnerable/fixed/expired HTTP fixtures |
| `tenantlens/reporting.py` | JSON and escaped HTML reports |
| `tenantlens/static/` | Ready-to-run frontend bundle |
| `web/` | React + TypeScript source, lockfile and browser smoke test |
| `tests/` | Decision, HTTP integration, privacy and boundary checks |
| `examples/` | Token-free demo/custom project definitions |
| `scripts/package_release.py` | Clean ZIP packager |

## License

MIT. Bundled third-party notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

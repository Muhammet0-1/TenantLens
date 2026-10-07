# Contributing

Start with [README.md](README.md) and [docs/architecture.md](docs/architecture.md).

Run the dependency-free Python tests:

```sh
python3 -S -m unittest discover -s tests -v
```

Frontend development requires Node 22.12+ or Node 24 and access to npm:

```sh
cd web
npm ci
npm run build
npx playwright install chromium
npm run test:browser
```

For live frontend development, start `python3 -m tenantlens serve --demo` from
the project root, then run `npm run dev` from `web` in a second terminal. Vite
proxies `/api` to port 8765. Browser checks use a temporary workspace on 18765
and three demo targets on the following ports. `PYTHON` selects the interpreter;
`TENANTLENS_TEST_PORT` changes the panel port.

Keep the verdict engine independent of the panel. A change to decision rules
needs a regression test showing the concrete false positive or false negative
it prevents. Avoid tests that assert private implementation details.

Do not commit credentials, private targets, SQLite state or reports from real
systems. Screenshots committed to this repository must use the local demo.
Do not weaken identity, baseline, scope, TLS or evidence checks to make a test pass.

Open a pull request describing the changed behavior and the validation you ran.

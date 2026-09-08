# Workspace regression checks

These tests use an isolated SQLite database and synthetic records. They never connect to production.

Install the project's development dependencies, then run from the repository root:

```sh
python -m pytest tests/workspace_regression --confcutdir=tests/workspace_regression -q -p no:cacheprovider -o asyncio_default_fixture_loop_scope=function -o asyncio_default_test_loop_scope=function
```

They exercise the real lawyer API permission checks, assignment filtering, restricted director responses, settlement validation, cent allocation and persisted updates limited to the selected shop and order.

Frontend checks, from `frontend`:

```sh
npx vue-tsc -p tsconfig.app.json --noEmit
npx vite build
npm run test -- --run tests/unit/payment-register.spec.ts
```

For browser checks, start Vite on localhost port 5177 and run `node tests/browser/workspace-smoke.cjs`. The script uses Playwright and headless Edge by default. Set `PLAYWRIGHT_MODULE_PATH` to an installed Playwright module when it is not in the local dependencies; `TEST_ORIGIN` and `BROWSER_CHANNEL` override the local URL and browser. All API calls are mocked. The script checks payment editing, modal scrolling on desktop and small screens, and accountant read-only cards, and saves screenshots in the system temporary directory. The server suite separately verifies that unassigned data cannot be retrieved.

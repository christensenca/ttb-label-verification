# Playwright end-to-end tests

These specs drive the real React UI against a real FastAPI backend through
Chromium. They cover the deploy-readiness flows the team cares about: upload,
processing, approval, and changing pass status via override.

| Spec | Flow |
| ---- | ---- |
| [upload_to_approve.spec.ts](upload_to_approve.spec.ts) | Upload a new item → click Run → wait for Ready → Approve (with confirmation modal). |
| [override_to_pass.spec.ts](override_to_pass.spec.ts) | Upload with a wrong brand → Run → see Fail → **override Fail→Pass** with comment → Approve cleanly. |
| [override_to_fail.spec.ts](override_to_fail.spec.ts) | Upload with all matching fields → Run → all Pass → **override Pass→Fail** with comment → Reject with that field as the structured reason. |

The two pytest e2e suites under `tests/integration/` cover the same workflow
through the API layer (faster, deterministic, runs in CI). These Playwright
specs sit on top and verify the *UI wiring* — selectors, modal flow, table
state machine, polling.

## How to run

The Playwright specs need three things running:

1. **Postgres** — a database, port 55432 in the example below.
2. **FastAPI with the stub extractor** — uvicorn launched via
   [scripts/serve_with_stub_extractor.py](../../../scripts/serve_with_stub_extractor.py),
   which patches the vision call with a deterministic Don Julio response so
   tests don't burn OpenRouter credits. Defaults to port 8001.
3. **Vite dev server** — the SPA, port 5174, with its `/api` proxy pointed at
   the stub backend via `E2E_API_URL=http://127.0.0.1:8001`.

Concretely:

```sh
# 1. Postgres
docker run -d --name ttb-pg-e2e \
  -e POSTGRES_USER=ttb -e POSTGRES_PASSWORD=ttb -e POSTGRES_DB=ttb_verify \
  -p 55432:5432 postgres:16

# 2. Migrations + stub backend
cd /Users/cadechristensen/Source/ttb-label-verfication
DATABASE_URL="postgresql+psycopg://ttb:ttb@localhost:55432/ttb_verify" \
  uv run alembic upgrade head

DATABASE_URL="postgresql+psycopg://ttb:ttb@localhost:55432/ttb_verify" \
IMAGE_STORAGE_DIR=/tmp/ttb-e2e-images \
CORS_ALLOWED_ORIGINS="http://localhost:5174,http://127.0.0.1:5174" \
E2E_HOST=127.0.0.1 E2E_PORT=8001 \
  uv run python scripts/serve_with_stub_extractor.py

# 3. Vite (in another shell)
cd frontend
E2E_API_URL=http://127.0.0.1:8001 pnpm dev --host 127.0.0.1 --port 5174

# 4. Playwright (in another shell)
cd frontend
E2E_BASE_URL=http://127.0.0.1:5174 E2E_API_URL=http://127.0.0.1:8001 \
  pnpm test:e2e
```

`beforeEach` in each spec calls `POST /api/admin/reset` so the queue starts
in a known state regardless of prior runs.

The Playwright config (`playwright.config.ts`) does **not** auto-start any of
the three sidecars — the assumption is that you've already brought them up
once and `pnpm test:e2e` runs against them. This keeps iteration fast and
lets the same Playwright run target a deployed staging environment by setting
`E2E_BASE_URL` and `E2E_API_URL`.

## What the stub extractor does

The launcher in [serve_with_stub_extractor.py](../../../scripts/serve_with_stub_extractor.py)
monkey-patches `pipeline.extract.extract` at process start, returning a fixed
Don Julio extraction regardless of the input image. That means:

- Submissions whose expected values match Don Julio's canned output → every
  field naturally passes.
- Submissions with one mismatching field → that field fails on its own.
- The test author controls which fields pass or fail by varying the
  `expected_values` JSON in the upload form.

Do **not** run the stub launcher in production — it bypasses the real vision
model.

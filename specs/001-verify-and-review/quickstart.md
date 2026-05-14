# Quickstart: Verify-and-Review

This describes how to run, develop, and verify the verify-and-review workflow once
implemented. It is written so an engineer who has never seen the repo can stand up
the local dev loop in under ten minutes.

---

## Prerequisites

- Python 3.11+ (`uv` is the existing project's package manager; `pip` works too)
- Node 20+ and `pnpm` (or `npm`)
- PostgreSQL 14+ running locally (or use the Docker compose snippet below)
- An OpenRouter API key (the pipeline calls OpenRouter directly; swapping providers is
  out of scope for this feature — see plan Complexity Tracking)

---

## Environment

Copy `.env.example` to `.env` and fill in the real values:

```dotenv
OPENROUTER_API_KEY=sk-or-...                    # OpenRouter key (read by pipeline/extract.py)
OPENROUTER_MODEL=google/gemini-3.1-flash-lite   # default if unset
EXTRACTION_CONCURRENCY=3                        # background-task semaphore

DATABASE_URL=postgresql+psycopg://ttb:ttb@localhost:5432/ttb_verify
IMAGE_STORAGE_DIR=./.local/images

CORS_ALLOWED_ORIGINS=http://localhost:5173
```

---

## Local DB (option A — Docker)

```sh
docker run -d --name ttb-pg \
  -e POSTGRES_USER=ttb -e POSTGRES_PASSWORD=ttb -e POSTGRES_DB=ttb_verify \
  -p 5432:5432 postgres:16
```

## Local DB (option B — Homebrew)

```sh
brew install postgresql@16
brew services start postgresql@16
createuser -s ttb && createdb -O ttb ttb_verify
```

---

## Backend bootstrap

```sh
uv sync                                    # install Python deps from pyproject.toml
uv run alembic upgrade head                # apply schema migrations
uv run python -m app.db.seed               # idempotent fixture seed
uv run uvicorn app.main:app --reload       # dev server on :8000
```

You should now have:
- 7 fixture submissions in `loaded` status
- 7 images copied to `IMAGE_STORAGE_DIR`
- API responding at `http://localhost:8000/healthz` and `http://localhost:8000/api/submissions`
- OpenAPI docs at `http://localhost:8000/docs`

---

## Frontend bootstrap

```sh
cd frontend
pnpm install
pnpm gen:api                               # regenerate typed client from OpenAPI
pnpm dev                                   # Vite dev server on :5173
```

Open `http://localhost:5173`. You should see seven `Loaded` items and a **Start** button.

---

## Smoke test the happy path

1. Open `http://localhost:5173`.
2. See 7 fixture items in `Loaded` state. The shared-demo banner is visible.
3. Click **Start**. Items transition `Loaded → Processing → Ready for Review` within
   ~10–20 seconds total (3 in flight at a time, ~3–5s each).
4. Open the first item. Verify:
   - Image on the left, fields on the right.
   - Fields grouped: Identity, Producer, Quantitative, Origin, Government Warning.
   - Each row shows Extracted | Expected | verdict pill | rule label | confidence cue.
   - At least one row has a green Pass; at least one fixture should produce a Fail with
     an inline word-diff visible in both columns.
5. Click a failing field → image lightbox opens at a readable size.
6. Click **Override to Pass** on a failed field → comment prompt → override visible.
7. Scroll to bottom. Add a comment. Click **Approve** → if any field remains in Fail,
   confirm the modal. Item moves to `Approved`.
8. Reload the page. Open the item again. Decision, comment, and any overrides persist.

Repeat with **Reject** on a different item: tick at least one failure-reason checkbox,
submit, reload, verify persistence.

---

## Run the test suites

Backend:

```sh
uv run pytest                              # all tests
uv run pytest tests/api                    # just API contract tests
uv run pytest tests/integration            # end-to-end queue → review flow
```

Frontend:

```sh
cd frontend
pnpm test                                  # Vitest unit tests
pnpm test:e2e                              # Playwright smoke (optional)
```

---

## Container build (mirrors production)

```sh
docker build -t ttb-verify .
docker run --env-file .env -p 8000:8000 \
  -v $PWD/.local/images:/data/images \
  ttb-verify
```

Open `http://localhost:8000`. Same flow as the dev environment; everything is served
from one container, one port. The container runs `alembic upgrade head` and the seed
step before starting uvicorn.

---

## Azure deploy (smoke)

```sh
az login
az containerapp up \
  --name ttb-verify \
  --resource-group ttb-rg \
  --location eastus \
  --source .
```

Set the same env vars (with `OPENAI_BASE_URL` pointing at Azure OpenAI if desired) via
the Azure portal or `az containerapp update --set-env-vars`.

---

## Demo reset

Either:
- Click **Reset demo** in the UI footer and confirm.
- `curl -X POST -H 'Content-Type: application/json' -d '{"confirm": true}' \
   http://localhost:8000/api/admin/reset`

User-added items are deleted; fixtures return to `Loaded`. Image storage for user-added
items is cleaned up.

---

## Verifying constitutional gates

These checks should all pass at every commit:

- `uv run pytest` — green.
- `uv run ruff check pipeline app tests` — clean.
- `cd frontend && pnpm typecheck && pnpm test` — green.
- Manual: open the deployed instance, run the smoke test in this file, confirm the
  shared-demo banner is visible.

The 5-second SLA is verified by reading `extractions.latency_ms` after a Start run;
p95 should be ≤ 5000.

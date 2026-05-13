# TTB Label Verification

AI-powered prototype for verifying TTB alcohol beverage labels against
application data. Take-home project for the TTB compliance division.

## What this is

A single-container web app that lets a reviewer:

1. Drop in a label image plus the expected values (brand, alcohol content,
   producer, government warning, etc.).
2. Hit **Run** and watch a vision model extract values from the image and
   compare them to the expected ones, field by field.
3. Review the per-field verdicts with inline word-diffs on text mismatches,
   open the source image at readable size, override a verdict with a comment,
   and approve or reject the submission with structured reasons.

Seven preloaded fixtures ship with the app; reviewers can also add their own
items and reset the demo to its original state.

## Stack

| Layer    | Tech                                                            |
| -------- | --------------------------------------------------------------- |
| Backend  | Python 3.11, FastAPI, SQLAlchemy 2.x, Alembic, asyncio          |
| Pipeline | `pipeline/` — vision extraction + comparison + normalization    |
| Storage  | PostgreSQL + filesystem image store (`IMAGE_STORAGE_DIR`)       |
| Frontend | React 19, Vite, TypeScript, TanStack Query, React Router        |
| Deploy   | Single Docker image; Railway today, `az containerapp up` ready  |

Everything (API, SPA, static assets) is served from one container on one port.
No Redis, no Celery, no external queue — background processing is an asyncio
task pool with a configurable concurrency semaphore.

## Environment

Copy `.env.example` to `.env` and fill in real values:

```dotenv
OPENROUTER_API_KEY=sk-or-...                    # vision model key
OPENROUTER_MODEL=google/gemini-3.1-pro-preview  # default if unset
EXTRACTION_CONCURRENCY=3                        # background-task semaphore

DATABASE_URL=postgresql+psycopg://ttb:ttb@localhost:5432/ttb_verify
IMAGE_STORAGE_DIR=./.local/images

CORS_ALLOWED_ORIGINS=http://localhost:5173
```

The full bootstrap walk-through (DB setup, dev servers, smoke test, container
build, test suites) lives in [specs/001-verify-and-review/quickstart.md](specs/001-verify-and-review/quickstart.md).

## Layout

```
pipeline/      # extraction + comparison library (pure Python, no HTTP/UI)
app/           # FastAPI app: API, persistence, services, Alembic migrations
frontend/      # React + Vite SPA, served from app/ in production
test_data/     # label images + expected-values JSON for eval and fixtures
tests/         # backend unit, contract, and integration tests
specs/         # feature specs, plan, tasks, contracts (Spec Kit)
reports/       # eval output (committed)
docs/          # planning notes and architecture decisions
```

## Quick start

```sh
uv sync
uv run alembic upgrade head
uv run python -m app.db.seed
uv run uvicorn app.main:app --reload      # API on :8000
```

```sh
cd frontend
pnpm install
pnpm gen:api
pnpm dev                                  # SPA on :5173
```

Open <http://localhost:5173>, click **Run**, and review the seeded fixtures.

## Test & lint

```sh
uv run pytest                              # backend
uv run ruff check pipeline app tests       # backend lint
cd frontend && pnpm typecheck && pnpm test # frontend type + unit
cd frontend && pnpm test:e2e               # Playwright happy-path (optional)
```

## Container & cloud

```sh
docker build -t ttb-verify .
docker run --env-file .env -p 8000:8000 \
  -v $PWD/.local/images:/data/images \
  ttb-verify
```

Deploy to Azure Container Apps (mirrors what production would look like):

```sh
az login
az containerapp up \
  --name ttb-verify \
  --resource-group ttb-rg \
  --location eastus \
  --source .
```

Set the env vars listed above via `az containerapp update --set-env-vars`.

## Docs

- [Quickstart](specs/001-verify-and-review/quickstart.md) — full bootstrap walk-through
- [Spec](specs/001-verify-and-review/spec.md) — user stories and acceptance scenarios
- [Plan](specs/001-verify-and-review/plan.md) — tech choices and architecture
- [Data model](specs/001-verify-and-review/data-model.md) — DB schema
- [API contract](specs/001-verify-and-review/contracts/api.md) — endpoint shapes
- [Constitution](.specify/memory/constitution.md) — engineering principles
- [Assignment brief](assigment.md) — original problem statement
- [Interview highlights](docs/interview-highlights.md) — domain context
- [Architecture decisions](docs/architecture-decisions.md) — recorded trade-offs

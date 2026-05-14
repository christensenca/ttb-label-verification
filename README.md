# LabelGuard

AI-powered prototype for verifying TTB alcohol beverage labels against
application data. Take-home project for the TTB compliance division.

## Approach

- Reviewer uploads a label image plus expected values (single form or
  batched CSV manifest of up to 100 rows).
- One vision-LLM call per label extracts the seven TTB-required fields
  plus Government Warning text and bold style, returned as a
  schema-enforced structured object.
- The pipeline normalizes both sides (case, units, abbreviations) and
  compares with deterministic per-field rules — fuzzy match for text,
  numeric tolerance for ABV, strict equality for the warning text.
- Each submission lands in a review queue; a human reviewer approves,
  rejects with structured reasons, or overrides any verdict with a
  free-text comment. Model verdicts are preserved alongside overrides
  for audit.
- Background extraction runs as an in-process asyncio task pool gated
  by a configurable concurrency semaphore — one container, one port,
  no Celery / Redis / external queue.

Full request lifecycle, status state machine, and per-field rules:
[docs/APPROACH.md](docs/APPROACH.md).

## Assumptions

- Input is one label image per submission (JPEG / PNG / WebP) plus a
  CSV manifest of expected values for batches (or a JSON form for a
  single upload). No PDF intake.
- Labels are English; the Government Warning is checked against the
  canonical 27 CFR 16.21 wording.
- The seven core required fields apply across beer, wine, and spirits
  (27 CFR Parts 4 / 5 / 7) — the schema generalizes even though our
  test corpus is distilled spirits.
- A human reviewer is always in the loop. The model proposes; it
  never auto-approves.
- Reviewers can override any verdict with a free-text comment;
  overrides persist alongside the model output so the audit trail
  shows both.
- Comparison is deterministic per-field (fuzzy match, numeric
  tolerance, unit-aware, strict for the warning) — no LLM-as-judge.
- The UI is intentionally simple — clean enough for a non-technical
  agent (Sarah's "my mother could figure it out" benchmark from the
  stakeholder interviews).
- Outbound network to a hosted vision model (OpenRouter today,
  Azure OpenAI in production) is available from the container.

What we *deliberately* gave up to ship this scope:
[docs/TRADEOFFS.md](docs/TRADEOFFS.md).

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

- [Approach](docs/APPROACH.md) — request lifecycle, status state machine, per-field rules
- [Tradeoffs and limitations](docs/TRADEOFFS.md) — what we gave up and what production would change
- [Architecture decisions](docs/architecture-decisions.md) — what we chose and why
- [Quickstart](specs/001-verify-and-review/quickstart.md) — full bootstrap walk-through
- [Spec](specs/001-verify-and-review/spec.md) — user stories and acceptance scenarios
- [Plan](specs/001-verify-and-review/plan.md) — tech choices and architecture
- [Data model](specs/001-verify-and-review/data-model.md) — DB schema
- [API contract](specs/001-verify-and-review/contracts/api.md) — endpoint shapes
- [Constitution](.specify/memory/constitution.md) — engineering principles
- [Assignment brief](assigment.md) — original problem statement
- [Interview highlights](docs/interview-highlights.md) — domain context

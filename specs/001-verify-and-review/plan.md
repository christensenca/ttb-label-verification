# Implementation Plan: Verify-and-Review Workflow

**Branch**: `001-verify-and-review` | **Date**: 2026-05-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-verify-and-review/spec.md`

## Summary

Build the end-to-end verify-and-review workflow on top of the existing extraction +
comparison library (`pipeline/`). The user-facing surface is a single-page web app with
two screens: **Queue** (preloaded + user-added submissions, single **Start** action) and
**Review** (per-label, grouped fields, two-column extracted/expected, inline diffs on
text mismatches, image lightbox, per-field override, item-level Approve/Reject with
structured reject reasons and comments).

Technical approach: FastAPI backend that imports the existing `pipeline` package as a
library (no rewrite), Postgres persistence behind SQLAlchemy + Alembic, image storage
on a Railway volume behind a small storage interface, React + Vite + TypeScript
frontend served as static assets from the same FastAPI container. Background processing
uses FastAPI/asyncio background tasks with a concurrency semaphore — no external queue,
no Celery, no Redis (simplicity principle). The UI polls submission status every ~1.5s
during processing. A small word-level diff helper, written in Python and surfaced in
the comparison response, drives the inline diff highlighting in the review UI.

## Technical Context

**Language/Version**: Python 3.11 (backend, matches existing `pipeline/`); TypeScript 5.x +
Node 20 (frontend build tooling only — no runtime Node in production).

**Primary Dependencies**:
- Backend new: FastAPI, SQLAlchemy 2.x, Alembic, asyncpg (or psycopg3), pydantic-settings,
  python-multipart (image upload).
- Backend existing (reused as-is): openai, pillow, pydantic, python-dotenv, rapidfuzz —
  all already in `pyproject.toml`.
- Frontend: React 18, Vite, TypeScript, TanStack Query (status polling + cache),
  React Router (two routes), `openapi-typescript` (generate typed client from FastAPI's
  OpenAPI schema).

**Storage**:
- Database: PostgreSQL via SQLAlchemy ORM + Alembic migrations. `DATABASE_URL` env var
  (Railway Postgres add-on for demo, Azure Database for PostgreSQL portable).
- Images: filesystem under `IMAGE_STORAGE_DIR` (Railway volume), wrapped by a small
  `ImageStore` interface so Azure Blob can drop in later.

**Testing**:
- Backend: pytest (existing). New test layers: API contract tests against FastAPI
  TestClient, integration tests for the queue → process → review state machine using a
  mocked extractor (`pipeline.extract.extract` swapped via DI), unit tests for the new
  diff helper.
- Frontend: Vitest for component logic; minimal Playwright smoke for the two-screen
  happy path. UI behavior is mostly verified by manual walkthrough per Principle V.

**Target Platform**: Linux x86_64 container; single port; deploys to Railway today,
`az containerapp up` for Azure portable per the constitution.

**Project Type**: Web application (FastAPI backend serving a React/Vite SPA from the
same container, plus existing Python library at `pipeline/`).

**Performance Goals**:
- ≤5s p95 end-to-end per single-label extraction (constitution + spec SC-002 ceiling).
- Queue UI updates visible within ≤2s of state change (polling interval ~1.5s).
- Reviewer "decide a typical label" target ≤60s (spec SC-002).

**Constraints**:
- Single-container deploy; no external queue or cache.
- No auth, no PII handling (prototype scope per spec assumptions and constitution
  Principle I).
- Azure-portable per constitution Principle VI: env-var-driven config, ORM-only DB
  access, storage and DB behind interfaces.
- Concurrency limit on vision calls (semaphore, default 3) to avoid burning provider
  budget on accidental large batches. **Status transitions are NOT throttled**: on
  Start, every `loaded` submission flips to `processing` immediately in one SQL
  statement; the semaphore only limits how many vision calls run in parallel. See
  research R12 for the full safety analysis.
- Field rows render as a **tri-state color** (green / yellow / red) computed from
  effective verdict + extractor confidence + field type. Confidence is a side-cue, not
  a verdict. See research R11.

**Scale/Scope**:
- Prototype scale: queue holds dozens of items during a demo (7 fixtures + user adds).
- Spec edge-case mentions 200–300 items as the upper bound the queue must remain
  responsive at; we will not optimize past that.
- Two screens, ~10 React components, ~8 API endpoints.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against `.specify/memory/constitution.md` v1.0.1.

| Principle | Status | Notes |
|---|---|---|
| I. Simplicity & Prototype-Appropriate Scope (NON-NEGOTIABLE) | PASS | No external queue, no cache, no auth, no signed URLs. Single container. Background tasks in-process. New dependencies (FastAPI, SQLAlchemy, Alembic, React/Vite, TanStack Query) are all named in the architecture decisions doc as the chosen stack — not speculative. |
| II. Maintainability via Typed Contracts | PASS | Pydantic at the LLM boundary already exists. New API request/response models are Pydantic. SQLAlchemy ORM for all DB access (no raw SQL). Frontend types generated from FastAPI's OpenAPI schema (`openapi-typescript`). Single `app/config.py` for all env-var reads. |
| III. Testable, Programmatic Comparison (NON-NEGOTIABLE) | PASS | Comparison logic stays in `pipeline/` (already covered by `tests/test_compare.py` and `tests/test_normalize.py`). The new word-level diff helper gets its own unit tests. No LLM-as-judge introduced. Vision/LLM calls remain mocked in unit tests; live evaluation continues in the existing bench harness. |
| IV. Graceful Fallbacks & Human-in-the-Loop (NON-NEGOTIABLE) | PASS | FR-009 enforces no auto-accept (matches Principle IV invariant). Extraction failures produce a queued `Extraction Failed` item with synthesized `comparisons` rows so the review UI, override endpoint, and rejection endpoint all work unchanged — see research R13. Storage and DB are interface-first. |
| V. Intuitive, Evidence-Rich UX | PASS | Review screen design from spec (FR-011 through FR-018) directly implements the principle's "show extracted, expected, rule, and inline diff" requirement. Government Warning gets its own grouped block. Confidence renders as a subtle inline cue per Principle V and as one input to the row-level tri-state color (green / yellow / red) — see research R11. Non-text fields surface `confidence: null`; the UI omits the inline cue and never paints yellow for them. |
| VI. Azure-Portable by Construction | PASS *(with one tolerated deviation)* | Container-first multi-stage Dockerfile, env-var config for DB/storage/CORS, ORM at the DB boundary, storage behind an `ImageStore` interface. Deviation: `pipeline/extract.py` keeps its existing OpenRouter-specific env vars (`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`) and its hard-coded base URL, scoped out of this feature per user direction. Provider portability for the prototype therefore requires a one-line code edit rather than a one-env-var swap. Logged in Complexity Tracking below. |

**Performance & Operational Constraints**: 5s SLA achievable on one vision call (current
bench shows ~2–4s on Gemini 3.1 Pro). Single vision call per label preserved
(decision #11). Sync vs. async endpoint split is unchanged from decision #5 in spirit,
but in this prototype the "async" path is in-process background tasks, not a separate
job system — see research note R1.

**Development Workflow & Quality Gates**: New test layers added per Principle III.
Frontend types generated from OpenAPI per Principle II. New env vars added to
`.env.example` as a deliverable in tasks. Migrations atomic with model changes per
Principle II.

**One tolerated deviation** logged in Complexity Tracking below (provider env-var
naming in `pipeline/extract.py`).

## Project Structure

### Documentation (this feature)

```text
specs/001-verify-and-review/
├── plan.md              # This file (/speckit-plan command output)
├── spec.md              # Feature spec
├── research.md          # Phase 0 output (this command)
├── data-model.md        # Phase 1 output (this command)
├── quickstart.md        # Phase 1 output (this command)
├── contracts/           # Phase 1 output (this command)
│   └── api.md           # HTTP contract — endpoints, request/response shapes
├── checklists/
│   └── requirements.md  # From /speckit-specify
└── tasks.md             # Phase 2 output (/speckit-tasks command — NOT in this command)
```

### Source Code (repository root)

```text
# Existing — DO NOT MOVE
pipeline/
├── __init__.py
├── extract.py           # Vision-LLM extractor — REUSED AS-IS
├── compare.py           # Per-field comparison — REUSED AS-IS
└── normalize.py         # Text normalization — REUSED AS-IS

tests/                   # Existing pytest suite — REUSED, EXTENDED
├── test_extract.py
├── test_compare.py
├── test_normalize.py
├── test_bench_models.py
├── test_bench_replay.py
└── conftest.py

scripts/
└── bench_models.py      # Existing bench harness — UNTOUCHED

test_data/               # 7 fixture bottles + expected JSONs — REUSED AS DEMO FIXTURES
├── images/
└── expected/

# New — added by this feature
app/                     # FastAPI application
├── __init__.py
├── main.py              # FastAPI app instance, route registration, startup hooks
├── config.py            # pydantic-settings — ALL env-var reads live here
├── api/
│   ├── __init__.py
│   ├── submissions.py   # POST /submissions, GET /submissions, GET/POST detail
│   ├── decisions.py     # POST /submissions/{id}/decision, /override
│   ├── admin.py         # POST /admin/reset, /healthz
│   └── schemas.py       # Pydantic request/response models (API DTOs)
├── db/
│   ├── __init__.py
│   ├── models.py        # SQLAlchemy ORM models
│   ├── session.py       # Engine + session factory
│   └── seed.py          # Loads test_data/ into DB on first boot
├── services/
│   ├── __init__.py
│   ├── processor.py     # Background-task runner: orchestrates pipeline.extract + compare
│   ├── diff.py          # Word-level diff helper for failing text fields
│   ├── reviews.py       # Override + decision business logic
│   └── storage.py       # ImageStore interface + filesystem implementation
└── alembic/             # Alembic migrations
    ├── env.py
    └── versions/

tests/                   # Extended (same dir as existing)
├── api/
│   ├── test_submissions.py
│   ├── test_decisions.py
│   └── test_admin.py
├── services/
│   ├── test_processor.py    # Uses mocked pipeline.extract
│   └── test_diff.py
└── integration/
    └── test_queue_flow.py   # Load → Start → Ready → Approve, end-to-end on TestClient

frontend/                # React + Vite SPA
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/             # Generated client from OpenAPI + thin TanStack Query hooks
│   ├── pages/
│   │   ├── QueuePage.tsx
│   │   └── ReviewPage.tsx
│   ├── components/
│   │   ├── QueueTable.tsx
│   │   ├── AddSubmissionForm.tsx
│   │   ├── FieldGroup.tsx        # Identity / Producer / Quantitative / Origin / Warning
│   │   ├── FieldRow.tsx          # Two-column extracted | expected
│   │   ├── InlineDiff.tsx        # Renders the word-level diff tokens
│   │   ├── ImageLightbox.tsx
│   │   ├── OverrideDialog.tsx
│   │   ├── DecisionPanel.tsx     # Approve/Reject with structured reasons + comment
│   │   ├── ConfidenceBadge.tsx
│   │   ├── SharedDemoBanner.tsx
│   │   └── __tests__/   # Vitest component tests, colocated with components
│   └── styles/          # CSS Modules (per-component .module.css)
└── tests/
    └── e2e/             # Playwright smoke (one happy-path file)

# Repo root — new
Dockerfile               # Multi-stage: node build → python runtime
.env.example             # Documented env vars
docker-entrypoint.sh     # Runs Alembic migrations + seed on container start
```

**Structure Decision**: Web app with a Python library at `pipeline/`. The library stays
exactly where it is — the FastAPI app at `app/` imports it. Frontend lives at
`frontend/`, builds to `frontend/dist/`, which the Dockerfile copies into the FastAPI
image; FastAPI serves the SPA's static assets from a single port. Tests and migrations
sit alongside their respective code per the existing repository convention.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Provider env vars stay `OPENROUTER_*` with a hard-coded base URL in `pipeline/extract.py` (soft deviation from Principle VI's "one-env-var swap" target). | User scoped this out of the current feature. The pipeline is reused as-is; touching it during feature work risks regressions on the most-tested surface in the repo. | Renaming to `OPENAI_*` and reading `OPENAI_BASE_URL` would be a ~10-line refactor with mechanical test updates, but unrelated to the verify-and-review feature; appropriate as its own follow-up if/when a provider swap is actually needed. |
| Structured-output fallback to JSON mode is not implemented (deviation from Principle IV's "fallback path is documented and tested, not aspirational"). `pipeline/extract.py` calls `client.beta.chat.completions.parse()` exclusively. | The current default model (Gemini 3.1 Pro via OpenRouter) supports structured outputs, and the pipeline is reused as-is for this feature. The supported-model path is covered by the existing `tests/test_extract.py`. | Adding the fallback now would touch `pipeline/extract.py`, which is out of scope for this feature. The pipeline is the most-tested surface in the repo; modifying it during feature work risks regressions. Appropriate as a follow-up if/when a non-supporting model becomes a candidate (at which point the fallback should be added with its own test fixtures). |

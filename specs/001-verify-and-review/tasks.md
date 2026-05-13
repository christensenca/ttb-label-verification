---

description: "Task list for verify-and-review workflow"
---

# Tasks: Verify-and-Review Workflow

**Input**: Design documents from `/specs/001-verify-and-review/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [data-model.md](data-model.md), [research.md](research.md), [contracts/api.md](contracts/api.md), [quickstart.md](quickstart.md)

**Tests**: Included. Constitution Principle III (NON-NEGOTIABLE) requires test-first
discipline for comparison-adjacent logic (the diff helper), and the plan mandates
API contract tests and integration tests covering the queue → process → review state
machine.

**Organization**: Tasks are grouped by user story to enable independent implementation
and testing of each story. The existing `pipeline/` library (extraction + comparison
+ normalization) is reused unchanged — no tasks touch it.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Per [plan.md § Project Structure](plan.md): web app with Python library at
`pipeline/` (reused as-is), new FastAPI app at `app/`, new React frontend at
`frontend/`, backend tests under `tests/api/`, `tests/services/`,
`tests/integration/`, frontend component tests colocated under
`frontend/src/components/__tests__/`, and Playwright e2e under `frontend/tests/e2e/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, dependency declarations, build scaffolding.

- [X] T001 Add backend dependencies to `pyproject.toml`: `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2.0`, `alembic`, `psycopg[binary,pool]`, `pydantic-settings`, `python-multipart`, `httpx` (for TestClient). Update `uv.lock` via `uv sync`.
- [X] T002 [P] Create `.env.example` at repo root documenting every env var per [quickstart.md § Environment](quickstart.md): `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `EXTRACTION_CONCURRENCY`, `DATABASE_URL`, `IMAGE_STORAGE_DIR`, `CORS_ALLOWED_ORIGINS`.
- [X] T003 [P] Create `app/` package scaffold: `app/__init__.py`, `app/api/__init__.py`, `app/db/__init__.py`, `app/services/__init__.py`.
- [X] T004 [P] Scaffold `frontend/` with Vite + React + TypeScript: `cd /Users/cadechristensen/Source/ttb-label-verfication && pnpm create vite frontend --template react-ts`. Add deps: `react-router-dom`, `@tanstack/react-query`, `openapi-typescript` (dev). Commit `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`.
- [X] T005 [P] Create multi-stage `Dockerfile` at repo root per [research.md R6](research.md): stage 1 `node:20-alpine` builds `frontend/dist/`; stage 2 `python:3.11-slim` installs `uv` + Python deps, copies `pipeline/`, `app/`, `frontend/dist/`. CMD = `docker-entrypoint.sh`.
- [X] T006 [P] Create `docker-entrypoint.sh` at repo root: runs `alembic upgrade head`, then `python -m app.db.seed`, then `exec uvicorn app.main:app --host 0.0.0.0 --port 8000`. Make executable (`chmod +x`).
- [X] T007 Create `app/config.py` with `pydantic_settings.BaseSettings` reading every env var listed in T002. Single source of truth for config; nothing else reads `os.environ` directly.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Persistence layer, storage interface, FastAPI shell, frontend skeleton,
test harness. Must complete before ANY user story phase.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T008 Implement `app/db/session.py`: SQLAlchemy 2.x engine from `DATABASE_URL`, sessionmaker, `get_db` FastAPI dependency.
- [X] T009 Implement `app/db/models.py`: ORM classes `Submission`, `Extraction`, `Comparison`, `FieldOverride`, `Review` per [data-model.md](data-model.md). Include `__table_args__` for indexes.
- [X] T010 Initialize Alembic: run `alembic init app/alembic`; edit `app/alembic/env.py` to import `app.db.models.Base.metadata` and read `DATABASE_URL` from settings.
- [X] T011 Author the initial Alembic migration in `app/alembic/versions/` creating all 5 tables and every index listed in [data-model.md § Index summary](data-model.md). Verify with `alembic upgrade head` against a local Postgres.
- [X] T012 [P] Implement `app/services/storage.py`: `ImageStore` Protocol (`put`, `open`, `delete`) and `FilesystemImageStore(root: Path)` using `IMAGE_STORAGE_DIR`; keys are content-addressed `sha256:<hex>.<ext>` per [research.md R5](research.md).
- [X] T013 [P] Implement `app/api/schemas.py`: Pydantic DTOs for `ExpectedValues` (with `is_imported`/`country_of_origin` cross-field validation), `SubmissionListItem`, `FieldRowOut`, `FieldGroupOut`, `ExtractionOut`, `ReviewOut`, `SubmissionDetailOut`, `OverrideIn`/`OverrideOut`, `DecisionIn`/`DecisionOut`, `AdminResetIn`.
- [X] T014 Implement `app/main.py`: FastAPI instance, CORS middleware reading `CORS_ALLOWED_ORIGINS`, `/healthz` endpoint, mount `frontend/dist/` at `/` via `StaticFiles` with SPA fallback for non-`/api/*` paths, `Cache-Control: no-store` middleware for `/api/*`.
- [X] T015 Implement `app/main.py` lifespan: on startup, call the rescue routine in `app/services/processor.py` that flips any `status='processing'` submissions to `status='extraction_failed'` with `error='interrupted'`, then call `app.db.seed.run_seed()`.
- [X] T016 [P] Implement `app/db/seed.py`: idempotent fixture seeder reading `test_data/expected/*.json` + `test_data/images/*.jpg`. Inserts submission rows with `is_fixture=True` and `status='loaded'`; copies images via `ImageStore.put`. Skips if any `is_fixture=True` row already exists.
- [X] T017 [P] Frontend: configure `frontend/src/main.tsx` with `BrowserRouter` and `QueryClientProvider`; create `frontend/src/App.tsx` with layout shell, `<Outlet/>`, and routes for `/` (QueuePage placeholder) and `/items/:id` (ReviewPage placeholder).
- [X] T018 [P] Frontend: create `frontend/src/components/SharedDemoBanner.tsx` (persistent banner per FR-025) and include in `App.tsx`.
- [X] T019 [P] Frontend: add `gen:api` script to `frontend/package.json` running `openapi-typescript http://localhost:8000/openapi.json -o src/api/generated.ts`. Commit a placeholder `generated.ts` to keep imports happy until the backend is up.
- [X] T020 [P] Frontend: implement `frontend/src/api/client.ts` — thin fetch wrapper, typed against `generated.ts`. Surface a `useApi()` hook returning `{get, post, del}` helpers that throw on non-2xx.
- [X] T021 Extend `tests/conftest.py` with: `TestClient(app)` fixture, a `db_session` fixture using a transactional rollback per test, and a `mock_extract` fixture that monkeypatches `pipeline.extract.extract` to return a canned `ExtractionResult`. Reuse the cached fixtures in `tests/fixtures/extractions.json` where helpful.

**Checkpoint**: `uv run uvicorn app.main:app` boots; `/healthz` returns 200; `/openapi.json` is served; seed creates 7 fixture rows; frontend dev server renders the shell with banner and routes.

---

## Phase 3: User Story 1 — Run the demo with one click (Priority: P1) 🎯 MVP

**Goal**: Fresh visitor sees 7 fixture items in `Loaded`, clicks **Start**, watches
items transition to `Ready for Review`, opens any item, sees field results in
groups + two columns, and can Approve or Reject. (Spec AS 1.1–1.4.)

**Independent Test**: With no user uploads, click Start; all preloaded items
transition Loaded → Processing → Ready for Review; open the first item; verify the
review screen shows the image, expected values, extracted values, per-field
verdicts; click Approve; verify status persists across reload.

### Tests for User Story 1

> Write these FIRST, ensure they FAIL, then implement.

- [ ] T022 [P] [US1] Unit test for the word-diff helper in `tests/services/test_diff.py`: equal/added/removed token tagging, whitespace preservation, identical input → all-equal tokens, completely different input → all add/remove tokens.
- [ ] T023 [P] [US1] Unit test for processor success path in `tests/services/test_processor_success.py`: mocked `pipeline.extract` returns a known `ExtractionResult`; verify one `Extraction` row exists with `latency_ms`, `input_tokens`, `output_tokens`, `model`, `extracted_label`, and `field_confidence` matching the mocked result (per constitution Performance & Operational Constraints); verify 10 `Comparison` rows exist with correct verdicts and rules; verify status flips to `ready_for_review`; verify all writes happen in one transaction.
- [ ] T024 [P] [US1] Unit test for processor extraction-failure path in `tests/services/test_processor_failure.py` per [research.md R13](research.md): mocked extractor raises; verify the `Extraction` row has `error` set, 10 synthesized `Comparison` rows exist with `verdict='fail'` (or `not_applicable`) and `rule='extraction failed'`, status flips to `extraction_failed`.
- [ ] T025 [P] [US1] Contract test in `tests/api/test_submissions_list.py`: `GET /api/submissions` returns 7 fixture items, ordered by `created_at DESC`, each with `status`, `is_fixture`, `thumbnail_url`.
- [ ] T026 [P] [US1] Contract test in `tests/api/test_submissions_start.py`: with N items in `loaded`, `POST /api/submissions/start` returns 202 with `scheduled==N`; verify all flip to `processing` synchronously before the response returns; with zero loaded items, returns 200 with `scheduled==0`.
- [ ] T027 [P] [US1] Contract test in `tests/api/test_submissions_detail.py`: `GET /api/submissions/{id}` on a `ready_for_review` item returns the read-model payload per [data-model.md](data-model.md); on a `loaded` item returns the same envelope with empty `groups` and null `extraction`; on `extraction_failed` returns synthesized groups with `extraction.error` non-null per R13.
- [ ] T028 [P] [US1] Contract test in `tests/api/test_decisions.py`: `POST /api/submissions/{id}/decision` with `decision='approved'` persists, flips status to `approved`; second decision on same submission returns 409; approve with `rejection_field_ids` non-empty returns 400.
- [ ] T029 [P] [US1] Integration test in `tests/integration/test_queue_flow.py`: seed → list → start → poll until all `ready_for_review` → fetch detail → POST approve → reload list → verify final status. Uses `mock_extract`.
- [ ] T029a [P] [US1] Integration test in `tests/integration/test_mixed_batch.py` covering FR-010 and SC-006: start with 5 fixture items, configure `mock_extract` to take 0ms for items 1–2 and ~1s for items 3–5 (`asyncio.sleep`) with `EXTRACTION_CONCURRENCY=2`. Assert that `GET /api/submissions/{id}` for items 1 and 2 returns full review payloads (`status='ready_for_review'`, populated `groups`) while items 3–5 are still `processing` and reachable but with empty `groups`. Confirms reviewers can open completed items mid-batch.

### Implementation for User Story 1

- [ ] T030 [US1] Implement `app/services/diff.py` exposing `word_diff(extracted: str, expected: str) -> tuple[list[DiffToken], list[DiffToken]]` using `difflib.SequenceMatcher` on whitespace-split tokens. Token shape per [data-model.md § Word-diff format](data-model.md).
- [ ] T031 [US1] Implement `app/services/processor.py::process_submission(submission_id, db_session_factory)`: load submission → call `pipeline.extract` (via injected callable for testability) → call `pipeline.compare` → for each failing text field call `word_diff` → write one Extraction row populating `extracted_label`, `field_confidence`, `latency_ms`, `input_tokens`, `output_tokens`, and `model` from the `ExtractionResult` (per constitution Performance & Operational Constraints — cost/latency/model logged into the `extractions` table) → write 10 Comparison rows → flip submission status to `ready_for_review`. All writes happen in one transaction. Wrap the whole body in `try/except`; on failure write the failure-shaped Extraction (with `error` set, data columns null) and synthesized Comparison rows per R13, then flip status to `extraction_failed`.
- [ ] T032 [US1] Implement `app/services/processor.py::process_all_loaded()`: single `UPDATE submissions SET status='processing' WHERE status='loaded' RETURNING id` returns the ID list; for each id, `asyncio.create_task` running `process_submission` gated by a module-level `asyncio.Semaphore(EXTRACTION_CONCURRENCY)`. Per [research.md R12](research.md).
- [ ] T033 [US1] Implement `app/services/processor.py::rescue_processing_on_startup()`: flip any `status='processing'` rows to `extraction_failed` with `error='interrupted'`. Called from the lifespan in T015.
- [ ] T034 [US1] Implement `app/api/submissions.py::list_submissions`: `GET /api/submissions` returning the list shape from [contracts/api.md](contracts/api.md). Brand is derived from `submissions.expected_values->'brand'`.
- [ ] T035 [US1] Implement `app/api/submissions.py::start`: `POST /api/submissions/start` calls `process_all_loaded()`, returns 202 with `{scheduled, submission_ids}`.
- [ ] T036 [US1] Implement `app/api/submissions.py::get_submission`: `GET /api/submissions/{id}` assembles the full read-model: joins extraction + comparisons + reviews + field_overrides; computes `effective_verdict` (override wins if present) per [data-model.md § Effective verdict](data-model.md); groups fields into Identity / Producer / Quantitative / Origin / Government Warning.
- [ ] T037 [US1] Implement `app/api/submissions.py::get_image`: `GET /api/submissions/{id}/image` streams the image via `ImageStore.open` with the correct `Content-Type`.
- [ ] T038 [US1] Implement `app/api/decisions.py::create_decision`: `POST /api/submissions/{id}/decision`. Validates per [contracts/api.md § Item decision](contracts/api.md): reject requires non-empty `rejection_field_ids` referencing fail-verdict comparisons on this submission; approve forbids `rejection_field_ids`. Writes the `reviews` row and flips submission status, in one transaction. Returns 409 on duplicate decisions.
- [ ] T039 [US1] Register routers in `app/main.py`: `submissions.router` at `/api`, `decisions.router` at `/api`. Verify `/openapi.json` reflects the new endpoints.
- [ ] T040 [P] [US1] Frontend: regenerate `frontend/src/api/generated.ts` via `pnpm gen:api`.
- [ ] T041 [P] [US1] Frontend: `frontend/src/pages/QueuePage.tsx` — uses TanStack Query to fetch `/api/submissions`, refetch every 1500ms when any item is in `processing` (else off), renders `QueueTable`, and shows a **Start** button that calls `POST /api/submissions/start` and invalidates the queue query.
- [ ] T042 [P] [US1] Frontend: `frontend/src/components/QueueTable.tsx` — rows show status pill, brand, fixture/user origin, thumbnail, and a link to `/items/{id}`. Status pill color matches the canonical states.
- [ ] T043 [P] [US1] Frontend: `frontend/src/pages/ReviewPage.tsx` — fetches `/api/submissions/{id}`; renders `ImagePane` (left) + `<FieldGroup/>` for each group (right) + `<DecisionPanel/>` at the bottom. If `extraction.error` is set, renders `<ExtractionFailedBanner/>` at the top per R13. Shows "still processing" placeholder when status is `loaded` or `processing`.
- [ ] T044 [P] [US1] Frontend: `frontend/src/components/FieldGroup.tsx` — accepts `{name, fields}` and renders the section heading + rows. Renders `FieldRow` for each field. No diff highlighting or color yet (US3 enriches this).
- [ ] T045 [P] [US1] Frontend: `frontend/src/components/FieldRow.tsx` — two-column layout: Extracted | Expected, plus verdict pill, rule label. Render `"—"` placeholder when `extracted_value` is null. No tri-state color, no diff (US3 enriches).
- [ ] T046 [P] [US1] Frontend: `frontend/src/components/DecisionPanel.tsx` — minimal but fully-functional version: comment textarea, an **Approve** button (always enabled when status is `ready_for_review` or `extraction_failed`), and a **Reject** button (enabled only when ≥1 field has `effective_verdict === 'fail'`). On Reject, the UI auto-fills `rejection_field_ids` with every currently-failing comparison row's `id` and POSTs the decision; this satisfies the API's "≥1 reason" requirement so US1's Reject path actually succeeds (Spec AS 1.4). When all fields pass, the Reject button is disabled with a tooltip ("no failing fields to reject against"). US5 will replace the auto-fill with the per-field checkbox UI.
- [ ] T047 [P] [US1] Frontend: `frontend/src/components/ExtractionFailedBanner.tsx` — large prominent banner with the error text and copy per R13.

**Checkpoint**: Quickstart smoke test (steps 1–5 of [quickstart.md § Smoke test the happy path](quickstart.md)) passes end-to-end. Items are reviewable individually as they complete.

---

## Phase 4: User Story 3 — Review with confidence and diffs (Priority: P1)

**Goal**: Field rows render with tri-state color (green/yellow/red per R11), inline
word-diff highlighting on failing text fields, and confidence cues on text fields
with low/med confidence. (Spec AS 3.1–3.4.)

**Independent Test**: Open a fixture whose Government Warning fails by one word; see
the missing word highlighted in both columns; confirm a pass row with `confidence:hi`
is green, a pass row with `confidence:low` on a text field is yellow, a fail row is
red, and `government_warning_style` (no confidence) is never yellow.

### Tests for User Story 3

- [ ] T048 [P] [US3] Frontend component test in `frontend/src/components/__tests__/InlineDiff.test.tsx` (Vitest): renders all three token kinds with distinct class names; preserves whitespace; renders empty when token list is empty.
- [ ] T049 [P] [US3] Frontend test in `frontend/src/components/__tests__/FieldRow.test.tsx`: row classes resolve to green/yellow/red per the truth table in [research.md R11](research.md) — `(pass, hi, text) = green`, `(pass, low, text) = yellow`, `(pass, null, non-text) = green`, `(fail, *, *) = red`, `(not_applicable, *, *) = grey`.

### Implementation for User Story 3

- [ ] T050 [US3] Frontend: implement `frontend/src/components/InlineDiff.tsx` — accepts `tokens: DiffToken[]`, renders each token as a `<span>` with class `diff-equal`/`diff-added`/`diff-removed`. CSS module styles highlight `added`/`removed` differently.
- [ ] T051 [US3] Frontend: enrich `FieldRow.tsx` to render `<InlineDiff/>` in the Extracted column from `diff_extracted` and in the Expected column from `diff_expected` when present (only on `verdict='fail'` text fields per [contracts/api.md](contracts/api.md)).
- [ ] T052 [US3] Frontend: implement `frontend/src/components/FieldRow.module.css` (or a `rowColorClass(field)` helper) deriving the tri-state class from `(effective_verdict, confidence, field_kind)` per R11. Apply as a CSS class on the row container.
- [ ] T053 [P] [US3] Frontend: implement `frontend/src/components/ConfidenceBadge.tsx` — small inline badge rendered for text fields when `confidence in {"low", "med"}`. Subordinate visual weight per Principle V; hidden when `confidence in {"hi", null}`.
- [ ] T054 [US3] Frontend: integrate `ConfidenceBadge` into `FieldRow.tsx` after the Expected column.
- [ ] T055 [P] [US3] Frontend: `NotApplicable` styling in the row CSS — greyed-out row with "Not applicable" verdict label.

**Checkpoint**: Spec AS 3.1–3.4 pass during manual review of a fixture batch.

---

## Phase 5: User Story 2 — Add my own item (Priority: P1)

**Goal**: Reviewer uploads a new label image + expected-values JSON, item appears in
queue with `Loaded` status, Start processes it alongside fixtures.

**Independent Test**: From the queue, click Add, supply an image + valid JSON, see
the new item appear; click Start; verify the new item transitions to `ready_for_review`
alongside the fixtures.

### Tests for User Story 2

- [ ] T056 [P] [US2] Contract test in `tests/api/test_submissions_create.py`: valid multipart returns 201 with `{id, status: "loaded"}`; missing image → 400; non-JSON expected_values → 400; `is_imported=true` with empty `country_of_origin` → 400 with specific reason; oversize image (>10 MB) → 400; wrong content-type → 415.

### Implementation for User Story 2

- [ ] T057 [US2] Backend: implement `app/api/submissions.py::create_submission`: accepts `multipart/form-data` (`image` file + `expected_values` string), validates `ExpectedValues` schema (T013), stores image via `ImageStore.put`, inserts submission row with `is_fixture=False`, returns 201.
- [ ] T058 [P] [US2] Frontend: `frontend/src/components/AddSubmissionForm.tsx` — file input (image), textarea (JSON), submit. On submit calls `POST /api/submissions` and surfaces validation errors from the response body.
- [ ] T059 [US2] Frontend: integrate `AddSubmissionForm` into `QueuePage.tsx`; on success, invalidate the queue query so the new row appears.

**Checkpoint**: Spec AS 2.1–2.3 pass.

---

## Phase 6: User Story 5 — Approve/Reject with notes (Priority: P1)

**Goal**: Rejection opens a panel listing every effective-`fail` field as a checkbox;
at least one must be ticked; approving with remaining fails triggers a confirmation
modal. Decision, comment, and structured reasons persist across reload.

**Independent Test**: On a `ready_for_review` item with one failing field, click
Reject → see the checkbox list with that field → submit without ticking and observe
the disabled submit → tick and submit → reload and verify the decision, comment, and
selected reasons persist.

### Tests for User Story 5

- [ ] T060 [P] [US5] Contract test in `tests/api/test_decisions_reject_validation.py`: reject with empty `rejection_field_ids` → 400; reject with an id that doesn't belong to this submission → 400; reject with an id whose effective verdict is `pass` (model passed, OR override-to-pass present) → 400.
- [ ] T061 [P] [US5] Integration test in `tests/integration/test_reject_flow.py`: process item → 2 fields fail → reject with 2 reasons + comment → fetch detail → assert `review.decision == 'rejected'`, `review.comment == ...`, `review.rejection_field_ids` contains both ids.

### Implementation for User Story 5

- [ ] T062 [US5] Backend: extend `create_decision` (T038) to enforce that every id in `rejection_field_ids` belongs to this submission and has **effective verdict = fail** (considering existing `field_overrides`). Reject otherwise.
- [ ] T063 [US5] Frontend: enrich `DecisionPanel.tsx` — Reject button opens a panel listing every field whose `effective_verdict === 'fail'` as a checkbox keyed by comparison id; the submit button is disabled until ≥1 checkbox is ticked; comment textarea remains.
- [ ] T064 [US5] Frontend: implement `frontend/src/components/ApproveConfirmationModal.tsx` — when the user clicks Approve and one or more rows have `effective_verdict === 'fail'`, show the modal with "There are still N failing fields — approve anyway?" plus the field list; on confirm, POST the decision.
- [ ] T065 [US5] Frontend: render the persisted `review` block on `ReviewPage.tsx` when status is `approved`/`rejected` — show decision, comment, and (for rejections) the selected reason field labels. Decision controls become read-only.

**Checkpoint**: Spec AS 5.1–5.4 pass; reload survives.

---

## Phase 7: User Story 4 — Open the source image and override (Priority: P2)

**Goal**: Failing-field row offers a click to open the image at readable size and an
Override control that flips the verdict with a required comment. Override is
distinguishable from a model verdict and survives reload; the original model verdict
remains visible.

**Independent Test**: Open an item with a failed text field, open the image, click
Override to Pass, supply a comment; see the row update to an overridden-pass state
showing the original `fail` verdict alongside; reload the item and verify
persistence.

### Tests for User Story 4

- [ ] T066 [P] [US4] Contract test in `tests/api/test_overrides.py`: `POST /api/submissions/{id}/overrides` with valid `{field, override_verdict, comment}` → 200; empty comment → 400; unknown field → 400; second POST on same field replaces (UPSERT) the existing row; status outside `ready_for_review`/`extraction_failed` → 409.
- [ ] T067 [P] [US4] Contract test in `tests/api/test_overrides_delete.py`: `DELETE /api/submissions/{id}/overrides/{field}` → 204; subsequent `GET /api/submissions/{id}` shows `effective_verdict` reverted to `model_verdict`; deleting a non-existent override → 404.
- [ ] T068 [P] [US4] Integration test in `tests/integration/test_override_flow.py`: process item with one extracted-as-fail field → override to pass with comment → approve → reload → assert both the override (with comment) and the approval persisted, original model verdict still visible in the payload.

### Implementation for User Story 4

- [ ] T069 [US4] Backend: implement `app/api/overrides.py::create_override` (`POST`) with UPSERT semantics (delete-and-insert in one tx; preserves "one override row per field" UNIQUE constraint per data-model). Snapshots the original model verdict from the matching `comparisons` row.
- [ ] T070 [US4] Backend: implement `app/api/overrides.py::delete_override` (`DELETE`).
- [ ] T071 [US4] Backend: extract effective-verdict computation into `app/services/reviews.py::compute_effective_verdict(comparison, override)` — used by the detail endpoint payload (T036) and by the rejection-id validation (T062). Centralizes the rule.
- [ ] T072 [US4] Register `overrides.router` in `app/main.py`; regenerate `frontend/src/api/generated.ts`.
- [ ] T073 [P] [US4] Frontend: `frontend/src/components/ImageLightbox.tsx` — modal showing the image at large size; close on Escape / click-outside / X button.
- [ ] T074 [P] [US4] Frontend: `frontend/src/components/OverrideDialog.tsx` — modal with required comment textarea, `Override to Pass` and `Override to Fail` buttons; calls the override endpoint on submit.
- [ ] T075 [US4] Frontend: enrich `FieldRow.tsx` — clickable image affordance opens `ImageLightbox`; "Override" button on every row opens `OverrideDialog`; when an override is present, the row renders with the override-styled border per R11 and shows both the override verdict and the original model verdict (FR-020).
- [ ] T076 [US4] Frontend: handle override-delete affordance ("Remove override") on rows with an existing override.

**Checkpoint**: Spec AS 4.1–4.4 pass; override survives reload alongside the model verdict.

---

## Phase 8: User Story 6 — Reset the shared demo (Priority: P3)

**Goal**: A reset action wipes user-added items and review decisions and restores
the queue to the original fixture set in `Loaded`. Destructive — confirms first.

**Independent Test**: After approving/rejecting one fixture and adding one user
item, trigger reset; confirm the queue matches the original fixture set with all in
`Loaded` and the user item gone.

### Tests for User Story 6

- [ ] T077 [P] [US6] Contract test in `tests/api/test_admin_reset.py`: `POST /api/admin/reset` without `{confirm: true}` → 400; with confirm, deletes user submissions (and their cascades), resets fixtures to `loaded`, deletes user image keys, leaves fixture image keys.

### Implementation for User Story 6

- [ ] T078 [US6] Backend: implement `app/api/admin.py::reset_demo`: validates `confirm == true`; in one transaction, deletes all `submissions WHERE is_fixture=False` (FK cascades clean `extractions`, `comparisons`, `field_overrides`, `reviews`); for `is_fixture=True` rows, deletes related extractions/comparisons/overrides/reviews and resets `status='loaded'`; calls `ImageStore.delete` for user-added image keys.
- [ ] T079 [US6] Register `admin.router` in `app/main.py`; regenerate `frontend/src/api/generated.ts`.
- [ ] T080 [P] [US6] Frontend: `frontend/src/components/ResetDemoButton.tsx` — button in the QueuePage footer; opens a confirmation modal; on confirm, calls `POST /api/admin/reset` with `{confirm: true}` and invalidates all queries.
- [ ] T081 [US6] Frontend: place `ResetDemoButton` in `QueuePage.tsx` footer alongside the persistent demo banner.

**Checkpoint**: Spec AS 6.1–6.3 pass.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [ ] T082 [P] Frontend: Playwright happy-path smoke test in `frontend/tests/e2e/smoke.spec.ts` — boot the app, click Start, wait for `Ready for Review`, open an item, approve, verify status pill.
- [ ] T083 [P] Add structured-log observability in `app/services/processor.py`: emit a JSON log line per item on completion with `submission_id`, `model`, `latency_ms`, `input_tokens`, `output_tokens` (or `error`). This is **in addition to** persisting these fields on the `extractions` row in T031 — the log line is for stdout/cloud-log scraping, the row is the durable audit record.
- [ ] T084 [P] Run `uv run ruff check pipeline app tests` clean; fix any drift.
- [ ] T085 [P] Run `cd frontend && pnpm typecheck && pnpm test` clean.
- [ ] T086 Verify `/healthz` reports DB reachability (a `SELECT 1` round-trip) in addition to "alive."
- [ ] T087 Update the repo `README.md` with: stack summary, the OPENROUTER env vars, a pointer to [quickstart.md](specs/001-verify-and-review/quickstart.md), and the Azure deploy snippet from quickstart.
- [ ] T088 Run a full pass of `quickstart.md § Smoke test the happy path` against a freshly-built container (`docker build` + `docker run`). Confirm 5-second SLA: read `extractions.latency_ms` rows and assert p95 ≤ 5000.
- [ ] T089 Manual validation task for **SC-002** (decide a typical label in <60s): time a domain-aware reviewer (or stand-in evaluator) through five `ready_for_review` items with ≤2 overrides each, from opening the item to submitting Approve/Reject. Median must be under 60s. Record results in `specs/001-verify-and-review/validation.md` (create the file).
- [ ] T090 Manual validation task for **SC-003** (identify a text-field diff in <5s): on the same five-item sample, time how long the reviewer takes to identify the differing words on every failing text field — without opening the image. Pass criterion: ≥90% of attempts under 5 seconds. Record in `validation.md`.
- [ ] T091 Manual validation task for **SC-004** (override + approve a wrongly-failed field in <30s): pick or construct an item where the model fails a field that the label actually satisfies; time the override-to-approve workflow end-to-end. Median under 30s. Record in `validation.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies; start immediately.
- **Foundational (Phase 2)**: depends on Setup. BLOCKS all user-story phases.
- **User Story 1 (Phase 3 / P1 / MVP)**: depends on Foundational. Independent of other stories.
- **User Story 3 (Phase 4 / P1)**: depends on Foundational + US1 (review screen exists). The review payload's `diff_*` fields are populated in US1; US3 renders them.
- **User Story 2 (Phase 5 / P1)**: depends on Foundational. Touches only `POST /api/submissions` + the `AddSubmissionForm`; can run in parallel with US3 if staffed separately.
- **User Story 5 (Phase 6 / P1)**: depends on US1 (decision endpoint and DecisionPanel exist). Can run in parallel with US3/US2 after US1 is in.
- **User Story 4 (Phase 7 / P2)**: depends on US1 (effective-verdict computation in T036) and US5 (rejection validation in T062, since override changes effective verdict). Best scheduled after US5 lands.
- **User Story 6 (Phase 8 / P3)**: depends on US2 (because reset is meaningful only when users can add items) and US1 (because reset must restore fixtures to `loaded`). Can be scheduled last.
- **Polish (Phase 9)**: depends on all completed stories.

### Within Each User Story

- Tests are written and FAIL before implementation.
- Backend models / services before endpoints.
- Endpoints before frontend integration.
- Frontend components marked [P] can land in parallel.

### Parallel Opportunities

- **Setup**: T002, T003, T004, T005, T006 in parallel.
- **Foundational**: T012, T013, T016, T017, T018, T019, T020 in parallel after T008/T009/T011 land.
- **US1 tests**: T022, T023, T024, T025, T026, T027, T028, T029, T029a in parallel.
- **US1 frontend**: T041, T042, T043, T044, T045, T046, T047 in parallel after the backend in T030–T039 is up.
- **US3, US2**: can be staffed in parallel after US1.
- **Polish**: T082, T083, T084, T085 in parallel. T089–T091 are manual reviewer-timing tasks, run sequentially against the same five-item sample.

---

## Parallel Example: User Story 1 tests (T022–T029)

```bash
# Eight tests, eight different files — fire all together
Task: "Unit test diff helper in tests/services/test_diff.py"
Task: "Unit test processor success in tests/services/test_processor_success.py"
Task: "Unit test processor failure (R13) in tests/services/test_processor_failure.py"
Task: "Contract test GET /api/submissions in tests/api/test_submissions_list.py"
Task: "Contract test POST /api/submissions/start in tests/api/test_submissions_start.py"
Task: "Contract test GET /api/submissions/{id} in tests/api/test_submissions_detail.py"
Task: "Contract test POST /api/submissions/{id}/decision in tests/api/test_decisions.py"
Task: "Integration test queue → start → approve in tests/integration/test_queue_flow.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Setup (Phase 1).
2. Foundational (Phase 2).
3. User Story 1 (Phase 3).
4. **Stop and validate**: run [quickstart.md § Smoke test the happy path](quickstart.md) end-to-end. The review screen is plain (no color, no diffs, no structured-reject UI), but the loop works.
5. Deploy to Railway. Demo-able.

### Incremental Delivery (recommended order)

1. MVP (above).
2. + US3 — color and diffs make the review screen actually trustworthy. Big UX leap, small code.
3. + US5 — structured rejection reasons make the rejection audit trail useful.
4. + US2 — let evaluators bring their own labels.
5. + US4 — image lightbox + override. Necessary the first time a real label has poor extraction.
6. + US6 — reset, so the shared demo doesn't accumulate cruft.
7. Polish.

### Parallel Team Strategy

Two developers after Foundational lands:
- Dev A: US1 → US3 (review-screen track).
- Dev B (after US1 detail endpoint exists): US2 → US5 → US4.

---

## Notes

- The existing `pipeline/` library (extract + compare + normalize + their tests) is
  reused unchanged. No task touches `pipeline/`.
- The constitution mandates tests for the new diff helper (Principle III). API
  contract tests and integration tests for the queue-state machine are mandated by
  the plan. UI components have light coverage (Vitest where the logic is non-trivial,
  Playwright for one happy-path smoke); manual walkthrough per Principle V is the
  primary UX verification.
- Commit after each task or logical group; no batching unrelated changes per
  constitution.
- Migrations land in the same commit as the model change that requires them.

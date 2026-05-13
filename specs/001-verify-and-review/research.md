# Phase 0 Research: Verify-and-Review Workflow

Resolved technical questions raised by the plan. Each entry: **Decision**, **Rationale**,
**Alternatives considered**. Most major architecture decisions are pre-resolved in
[docs/architecture-decisions.md](../../docs/architecture-decisions.md) and inherited
here; this file documents the deltas needed to land the feature.

---

## R1 — Background processing topology (single-container, no queue)

**Decision**: Process submissions in FastAPI/asyncio background tasks, scheduled with
`asyncio.create_task` and gated by an `asyncio.Semaphore` (default concurrency 3, env-var
configurable via `EXTRACTION_CONCURRENCY`). When a request hits `POST /submissions/start`,
the handler flips all `Loaded` items to `Processing` in one transaction and schedules one
background task per item. Each task runs `pipeline.extract` → `pipeline.compare` → diff
helper → DB writes → status flip.

**Rationale**:
- Constitution Principle I (Simplicity): the prototype must not stand up Redis, Celery, or
  RQ. A semaphore-gated asyncio task pool keeps everything in one process.
- The vision call is I/O-bound (HTTPS to OpenRouter), so cooperative async parallelism
  is the right primitive.
- Decision #5 in the architecture doc says "async for batch." This satisfies the spirit
  (the UI does not block on a 25-minute round trip) without inventing infrastructure.
- Failure isolation: an exception in one task is caught, logged, and flips that item to
  `Extraction Failed` — never affects siblings.

**Rescue on startup**: any item left in `Processing` at app boot is flipped to
`Extraction Failed` with reason "interrupted" so the queue is never stuck.

**Alternatives considered**:
- *Celery + Redis broker*: production-grade, but explicitly out-of-scope per Principle I.
- *Synchronous processing inside the Start request*: would block HTTP for up to
  ~5s × N items; unacceptable for batches.
- *Sub-process pool*: pointless for I/O-bound vision calls; adds complexity.

---

## R2 — Status update mechanism (polling vs. SSE vs. WebSocket)

**Decision**: Client polls `GET /submissions` every 1.5 seconds while at least one item
is in `Processing`; switches to passive (no polling) once everything is in a terminal
state. TanStack Query handles the polling interval, dedup, and cache.

**Rationale**:
- One screen, predictable cadence, no auth complexity, no proxy quirks (Railway, Azure
  Container Apps both pass SSE but require extra config).
- 1.5s feels live to a human and is well within the 5-second per-label budget.
- Architecture decisions doc explicitly notes SSE/WebSocket complexity is out of scope
  for single-label.

**Alternatives considered**:
- *SSE*: cleaner UX but adds an endpoint, a long-lived connection, and proxy-config
  burden for marginal benefit at this scale.
- *WebSocket*: even more weight than SSE; pointless for read-only status.

---

## R3 — Word-level diff format

**Decision**: Add `app/services/diff.py` with a `word_diff(extracted: str, expected: str)`
function returning two parallel lists of typed tokens:

```python
DiffToken = {"text": str, "kind": Literal["equal", "added", "removed"]}
extracted_tokens: list[DiffToken]
expected_tokens: list[DiffToken]
```

Computed using Python's standard library `difflib.SequenceMatcher` over whitespace-split
tokens. Punctuation kept attached to its token (the existing `pipeline.normalize` is
where canonical comparison lives — diff is purely a UI helper).

The comparison response surfaces these token lists only for text fields where the
comparison verdict is `Fail`. For passing fields the lists are omitted.

**Rationale**:
- `difflib` is in the stdlib, zero new dependency, ~10 lines of code.
- Server-side computation keeps the source of truth in Python next to the comparison
  code, and the React component is a trivial map-and-style render (no client-side diff
  library needed).
- Word-level (not character-level) granularity matches FR-017 ("word-aware diff for the
  Government Warning"): a missing word in the canonical warning is the highest-value
  visual signal.

**Alternatives considered**:
- *Client-side diff library (e.g., `diff-match-patch`)*: adds JS dependency and risks
  drift from server's canonical comparison logic.
- *Character-level diff*: noisier visually; doesn't match the "missing word" failure
  mode that matters most for the warning.

---

## R4 — Frontend stack details

**Decision**:
- **Build/runtime**: Vite + React 18 + TypeScript 5.x (per architecture decision #3).
- **Routing**: React Router v6, two routes — `/` (queue) and `/items/:id` (review).
- **Data layer**: TanStack Query v5 for server state (queue list, item detail), with the
  polling-while-processing behavior in R2.
- **Type generation**: `openapi-typescript` against the FastAPI-generated schema. Run as
  a `pnpm` script; output committed under `frontend/src/api/generated.ts`.
- **Styling**: CSS Modules per component. No Tailwind, no UI kit. The screen count
  (two) does not justify the dependency.
- **Forms**: Native `<form>` with controlled inputs. No React Hook Form, no Formik —
  the add-submission form has two inputs (image + JSON).

**Rationale**: Each pick is the smallest plausible tool that does the job. The
constitution's simplicity principle rejects "popular stack out of habit" decisions.

**Alternatives considered**:
- *Next.js*: rejected in architecture decision #3 already; same reasoning applies.
- *Tailwind*: marginal value for two screens; adds build complexity.
- *SWR* instead of TanStack Query: equivalent; TanStack Query's polling/refetch API is
  slightly more ergonomic and is the more common choice.

---

## R5 — Image storage interface

**Decision**: A small `ImageStore` Protocol in `app/services/storage.py`:

```python
class ImageStore(Protocol):
    def put(self, content: bytes, content_type: str) -> str: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...
```

Initial implementation: `FilesystemImageStore(root: Path)` using `IMAGE_STORAGE_DIR`.
Keys are content-addressed (`sha256:.../label.jpg`) per architecture decision #7.
Fixtures are copied from `test_data/images/` into the volume on first boot when missing.
Submission rows store the key, not the absolute path, so an Azure Blob implementation is
a drop-in.

**Rationale**: Decision #7 explicitly calls for the storage interface; this is the
minimum surface that makes the swap trivial.

**Alternatives considered**:
- *Store binary in DB as bytea*: rejected — Postgres is not an image server, and image
  display via API would require a streaming endpoint anyway.
- *Skip the interface, write to disk directly*: rejected — Principle IV requires
  fallback paths to be small and isolated, not retrofitted.

---

## R6 — Static asset serving (one container, one port)

**Decision**: Multi-stage Dockerfile:
1. Stage 1 (`node:20-alpine`): `pnpm install`, `pnpm build` → `frontend/dist/`.
2. Stage 2 (`python:3.11-slim`): install Python deps, copy `pipeline/`, `app/`,
   `alembic/`, and `frontend/dist/`. Run FastAPI via uvicorn.

FastAPI mounts `frontend/dist/` at `/` via `StaticFiles`, with a catch-all route that
returns `index.html` for non-API paths (SPA routing). API endpoints under `/api/*` and
`/healthz`. `docker-entrypoint.sh` runs `alembic upgrade head`, then the seed step, then
exec's uvicorn.

**Rationale**: Architecture decision #4 specifies single container, single port. This is
the simplest topology that satisfies it.

**Alternatives considered**:
- *Two containers behind a reverse proxy*: more deploy surface for no benefit.
- *Vercel for frontend, Railway for backend*: splits the deploy story; rejected in
  architecture decision #4 already.

---

## R7 — Decision and override persistence model

**Decision**: A submission's lifecycle has three tables: `submissions`, `extractions`,
`comparisons`. Human input lives in `reviews` (one row per submission, item-level
decision + comment + rejection reasons as JSONB array of comparison row IDs) and
`field_overrides` (one row per overridden field with the original verdict, the human
decision, the reviewer comment, and a timestamp). Both `comparisons.verdict` and the
override are read by the UI; the "effective verdict" is computed at read time
(override wins if present). See `data-model.md` for the full schema.

**Rationale**:
- Keeping the model verdict and the human override as separate facts preserves the
  audit story (constitution Principle IV: "both model output and human decisions
  persist for audit").
- One table per concept; no foreign-key acrobatics.
- JSONB array for selected rejection reasons is a small Postgres-specific lean — the
  constitution allows it when the alternative (a join table for a tiny prototype) is
  pure overhead.

**Alternatives considered**:
- *Single `reviews` row with embedded per-field decisions as JSON*: harder to query and
  index later; rejected.
- *Mutate `comparisons.verdict` directly on override*: destroys audit trail; explicitly
  forbidden by Principle IV.

---

## R8 — Seeding strategy

**Decision**: On container startup (after `alembic upgrade head`), `app/db/seed.py`
checks whether any fixture submissions exist (identified by `is_fixture=True` on the
submissions row). If absent, it inserts one submission row per file in
`test_data/expected/`, copies the matching image into `IMAGE_STORAGE_DIR`, and leaves
each item in `Loaded` state. Idempotent across restarts. The `POST /admin/reset`
endpoint truncates user data, deletes user-added image keys, and re-runs the same seed.

**Rationale**: Decision #9 in architecture doc specifies preloaded fixtures shipped in
the container build, seeded on first boot. This is the smallest reasonable
implementation.

**Alternatives considered**:
- *SQL fixture inserts as part of Alembic migrations*: couples schema and data —
  rejected because reset would need a separate path anyway.
- *Manual one-off seed script the operator runs*: prototype is supposed to "just work"
  on first visit; an unattended seed is mandatory.

---

## R9 — Concurrency safety and partial-state handling

**Decision**:
- DB writes for status transitions use SQLAlchemy's `with_for_update()` on the
  submission row to avoid lost updates when a second request and a background task
  both touch the same item.
- Background tasks write extraction + comparisons + status flip in a single transaction
  per item.
- The reviewer's in-flight overrides and comments are saved on each interaction (one
  override = one POST); the spec's "partial state restored on return" requirement
  (Edge Cases) is satisfied by reading what's already persisted — no separate "draft"
  concept.

**Rationale**: Single source of truth (the DB), one transaction per write, no client-
side draft layer to keep in sync. This matches Principle II (typed contracts at
boundaries) and Principle I (no speculative features).

**Alternatives considered**:
- *Optimistic concurrency with version columns*: overkill for a single-reviewer
  prototype.
- *Client-side draft buffer for overrides*: doubles the persistence story; rejected.

---

## R10 — Approve-with-failures confirmation surface

**Decision**: The "approve while N fields are still failing" confirmation
(FR-023, AS 5.3, locked in by clarification on 2026-05-13) is a frontend-only modal.
The API accepts the approval regardless; the backend simply records the decision and
the snapshot of (model verdict, override status) per field. The audit story is in the
data; the speed-bump is in the UI.

**Rationale**: Splits enforcement cleanly — the audit-relevant fact is "what was the
state when the reviewer approved?", which the data captures unconditionally. Adding a
server-side gate would force a "force=true" query param or a separate endpoint for
the same data, which is more surface for no extra correctness.

**Alternatives considered**:
- *Server rejects approval unless all fields pass or are overridden*: tighter, but
  removes reviewer discretion that the clarification explicitly preserved.
- *Two endpoints (`/approve` and `/force-approve`)*: API surface bloat with no real
  difference in stored state.

---

## R11 — Confidence display and the field-row tri-state color

**Verdict vocabulary** (lock this down before reading the rest):

| Concept | Where it lives | Possible values |
|---|---|---|
| **Model verdict** | `comparisons.verdict` column | `pass`, `fail`, `not_applicable` |
| **Override verdict** | `field_overrides.override_verdict` column (row optional) | `pass`, `fail` |
| **Effective verdict** | Computed at read time: override if a row exists, else model. Surfaced on the API payload as `effective_verdict` | `pass`, `fail`, `not_applicable` |
| **UI display state** | Rendered class on the field row | `Pass`, `Fail`, `Overridden Pass`, `Overridden Fail`, `Not Applicable`, `Needs Attention` |

"Overridden …" and "Needs Attention" are **UI states only** — not stored values, not
verdicts. "Overridden Pass" / "Overridden Fail" appears when a `field_overrides` row
exists (whether the override flipped the model or simply agreed with it). "Needs
Attention" is the yellow row treatment defined below; it never corresponds to a
column value. Spec FR-014 ("Pass, Fail, Overridden, or Not Applicable") describes
*displayed* states, not the verdict enum.

**Decision**:
- The dominant visual on every field row is a **tri-state color** for the whole row:
  - **Red**: effective verdict is `fail`.
  - **Yellow**: effective verdict is `pass`, the field is textual, AND extractor
    confidence is `med` or `low`. Read as "passed but worth a closer look."
  - **Green**: effective verdict is `pass` AND either confidence is `hi` OR the field
    is non-textual (no confidence available).
  - **Overridden** verdicts are rendered with a distinct outline/border treatment over
    the underlying color, so both the original model verdict and the human override
    remain visible (FR-020).
  - **Not Applicable** is greyed out and is not part of the tri-state.
- The per-field `confidence` cue (e.g., "low ⚠") is still rendered inline as a small
  side-comment on text fields when applicable, but it is intentionally subordinate to
  the row color. Per the user: "it's like a side comment for the reviewer."
- Non-text fields — `is_imported` and the synthetic `government_warning_style` — have
  `confidence: null` in the API payload. The UI shows **no** small confidence cue for
  them and they can only be green or red (never yellow).

**Rationale**:
- Constitution Principle V says low confidence MUST be a subtle visual cue, not a
  blocking alert. Folding it into the row color satisfies the principle while keeping
  the reviewer's eye on the verdict, not on a separate badge.
- Synthesizing confidence for fields the extractor does not score (boolean
  `is_imported`, synthetic style flag) would be a fabrication. Honest absence is
  better than a fake number.
- Verdict stays binary (`pass` / `fail`) in the data model. The yellow state is purely
  a rendering bucket, not a new verdict — no schema growth.

**Alternatives considered**:
- *Show a confidence badge on every field, with "n/a" for non-text*: rejected as
  noise. The reviewer does not need to be told `is_imported` has no confidence score.
- *Derive a confidence value for non-text fields (e.g., average the two bold flags)*:
  rejected — fabrication. No signal to derive from.
- *Two-state row color (pass / fail) with confidence as a separate sidebar column*:
  rejected — the most useful signal ("the model passed it but is not sure") is
  exactly the kind of thing the row color should encode.

---

## R12 — Start semantics and concurrency safety

**Decision**:
- `POST /api/submissions/start` runs **one** DB transaction that flips every
  `loaded` submission to `processing` via a single
  `UPDATE submissions SET status='processing' WHERE status='loaded'`. The status
  transition itself is not throttled — all eligible items move to `processing`
  immediately.
- After that transaction commits, the handler schedules N background tasks (one per
  submission) via `asyncio.create_task`. Each task acquires a shared
  `asyncio.Semaphore` (default 3, configurable via `EXTRACTION_CONCURRENCY`) before
  invoking `pipeline.extract`.
- The endpoint returns 202 with the scheduled IDs immediately; the handler does not
  wait for any task to finish.

**Per-item lifecycle inside each background task**:
1. Acquire semaphore.
2. Call `pipeline.extract` against the image (the long-pole I/O step).
3. Call `pipeline.compare` on the result.
4. Compute word-level diffs for failing text fields (see R3).
5. In a single per-item transaction: insert one `extractions` row, insert one
   `comparisons` row per field, flip `submissions.status` to `ready_for_review`.
6. Release semaphore (via context manager).

If any step raises, the task's outer `try/except` writes an `extractions` row with the
error message and flips `submissions.status` to `extraction_failed` instead. Siblings
are unaffected.

**Safety properties**:
- **No shared mutable state**: each task closes over only the submission ID and creates
  its own DB session. No global dictionary, no shared object, no message bus.
- **Items transition independently**: task A finishing first writes its rows and flips
  *its* submission's status; task B is unaware. The UI's poll sees one item move to
  `Ready for Review` while others remain `Processing`. No "wait for the whole batch"
  semantics.
- **Per-item atomicity**: extraction + comparisons + status flip happen in one DB
  transaction. The UI can never see a `ready_for_review` row that's missing its
  comparisons.
- **Bulk status flip is SQL-atomic**: the Start handler's
  `UPDATE ... WHERE status='loaded'` either commits all rows or none. No partial state
  visible to readers.
- **Independent failure**: an exception in task A is caught by its own `try/except`.
  Task B keeps running. The failed item lands in `extraction_failed`; the rest are
  unaffected.
- **Startup rescue**: any `processing` items at app boot are flipped to
  `extraction_failed` with reason "interrupted" (see R1). No items can be stuck.

**What the user sees during a Start on 7 items with concurrency 3**:
- At t=0: all 7 items flip to `Processing` (visible on the next 1.5s poll).
- t≈3s: items 1–3 finish (in completion order, not submission order); each flips to
  `Ready for Review` as it finishes. Items 4–6 acquire semaphore slots and start.
- t≈6s: items 4–6 finish. Item 7 starts.
- t≈9s: item 7 finishes. All 7 in `Ready for Review`.

The user can open any item the moment it shows `Ready for Review` — no need to wait
for the batch.

**Concurrency model assumption**: single uvicorn worker for the prototype. If the
container is later configured with multiple workers, each worker has its own semaphore
and rescue routine; worst case is `3 × workers` concurrent vision calls. Acceptable at
prototype scale.

**Alternatives considered**:
- *Serial processing (no concurrency)*: rejected — a 7-item batch would take 14–28s
  end-to-end; defeats spec SC-006 ("items reviewable within seconds of completion").
- *Unbounded concurrency*: rejected — burns provider budget on a runaway upload and
  invites 429s from OpenRouter.
- *Throttle status transitions too* (only the first 3 flip to `Processing`, the rest
  stay `Loaded` until a slot opens): rejected — would lie to the UI. The reviewer
  would see 4 "Loaded" items that are about to start any second. Better to be honest
  that they are queued for processing.

---

## R13 — Extraction-failed review payload

**Decision**: When extraction fails for a submission, the processor still writes
comparison rows — one per known field, synthesized with:

| Column | Value |
|---|---|
| `verdict` | `fail` (or `not_applicable` if the field is irrelevant to the submission, e.g. `country_of_origin` on a domestic label) |
| `rule` | `"extraction failed"` |
| `extracted_value` | `null` |
| `expected_value` | populated from `submissions.expected_values` (or null for the synthetic `government_warning_style` field) |
| `reason` | `"no extraction available"` |
| `diff_extracted`, `diff_expected` | `null` |

The `extractions` row is written with the error string in `extractions.error` and
every data column null. The submission flips to `extraction_failed` in the same
per-item transaction (so a reader never sees a `extraction_failed` row without its
synthesized comparisons).

**Read-model shape for an `extraction_failed` item** (the same envelope as a
successful item):

- `extraction.error` is non-null. `extraction.latency_ms`, `tokens`, `model` reflect
  whatever was captured up to the failure (`model` is always present; the rest may be
  null).
- `groups` contains all 5 groups and all 10 fields. Each field row carries
  `extracted_value: null`, `model_verdict: "fail"` (or `"not_applicable"`),
  `rule: "extraction failed"`, `confidence: null`, `diff: null`, `override: null`.

**UI behavior** (frontend-only, no extra API):

- Prominent banner at the top of the review screen: "Extraction failed: \<error\>.
  The model could not read this label. Review the expected values against the image
  yourself and override per field, or reject the item with a reason."
- Field groups render in the normal layout. The Extracted column shows an em-dash or
  "(no extraction)" placeholder. The row color is red (per R11: verdict=fail → red,
  no confidence so no yellow).
- The normal override control is available on every row. "Override to Pass" on a
  synthesized row is a meaningful human statement — "I read the image and confirmed
  this matches" — and persists as a normal `field_overrides` row.
- The rejection panel (FR-022) lists every synthesized row whose effective verdict is
  still `fail` as a tickable reason; the reviewer can tick the relevant ones or all
  of them.

**Rationale**:
- Schema-uniform. Every submission carries the same row shapes regardless of
  outcome; no special-case columns, no nullable foreign keys, no second renderer.
- API-uniform. Override (`POST /api/submissions/{id}/overrides`) and decision
  (`POST /api/submissions/{id}/decision`) endpoints work without modification. The
  spec's "structured rejection reasons" property (FR-022) is satisfied because rows
  exist to point at.
- Audit-honest. Override-to-pass on an extraction-failed field reads correctly later:
  "Model failed to extract; human confirmed against image." That story is exactly
  what the human-in-the-loop principle (Constitution IV) is designed to preserve.
- Minimal UI work. One conditional banner; everything else flows through the
  existing row and decision components.

**Edge: the synthetic `government_warning_style` field**. No expected value exists for
it (it's validated against label rendering flags, not against expected_values), so the
synthesized row has `expected_value: null` and the rule string makes clear the field
applies to the canonical 27 CFR text style. It is treatable as a normal fail or
override target.

**Alternatives considered**:
- *Don't write comparisons on failure; render a separate "extraction failed" layout*:
  rejected. Doubles the renderer surface, forces the override and rejection APIs to
  grow a parallel "by field name" mode alongside the existing "by comparison id"
  mode, and the UI would need separate copy for "extraction succeeded but field
  failed" vs. "field has no extraction." More code, weaker uniformity.
- *Allow rejection without `rejection_field_ids` when status is `extraction_failed`*:
  rejected. Breaks the spec's "every rejection is structured" property and produces a
  weaker audit trail.
- *Mark synthesized rows with an `is_synthesized` boolean column*: rejected as
  premature. The rule string (`"extraction failed"`) already communicates the same
  information and is grep-friendly. Add the column only if a query genuinely needs
  it later.

---

## R14 — What stays untouched in `pipeline/`

**Decision**: `pipeline/extract.py`, `pipeline/compare.py`, and `pipeline/normalize.py`
are reused unchanged. No behavior change to extraction or comparison logic is in scope
for this feature. The existing `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` env vars are
kept as-is; the hard-coded OpenRouter base URL stands.

**Rationale**: Principle I — don't refactor adjacent code while shipping a feature. The
comparison logic is the most-tested surface in the repo; touching it during feature
work is asking for regressions.

**Alternatives considered**:
- *Move `pipeline/` under `app/`*: rejected. Keeping it at the top level documents that
  it is an independent library, importable by the bench harness, the API, and future
  CLI/eval surfaces.

---

## Open items (not blocking implementation)

- **Image lightbox modality** (lightbox vs. side panel vs. fullscreen overlay): UX
  detail to settle during frontend implementation. The contract is "open large enough
  to read without leaving the review screen" (FR-018), implementation TBD.
- **User-add expected-values input shape** (file-upload of JSON vs. paste-box vs. form):
  the spec leaves this open; deferred to `/speckit-tasks` or implementation. Initial
  plan: a single textarea for JSON paste plus a separate file input for the image.
  Cheapest path; can grow into a form if reviewers struggle.

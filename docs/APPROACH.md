# Approach

How LabelGuard actually works — request lifecycle, pipeline stages,
status state machine, per-field comparison rules, and failure
recovery. The [README](../README.md) has the brief; this doc has the
detail.

For *why* we made these choices, see
[architecture-decisions.md](architecture-decisions.md) (eleven ADRs)
and [TRADEOFFS.md](TRADEOFFS.md).

---

## System shape

One FastAPI container serves the JSON API, the React SPA, and the
static label images. Postgres holds the submission queue, model
output, and reviewer decisions. Images live on a mounted volume,
content-addressed by sha256.

```
            ┌──────────────────────────────────────┐
   user ──▶ │  FastAPI (one container, one port)   │
            │                                      │
            │  ┌── React SPA (built into image)    │
            │  ├── /api/*  (submissions, reviews)  │
            │  ├── /images/*  (filesystem serve)   │
            │  └── asyncio task pool ── OpenRouter │
            └──────────────────────────────────────┘
                    │              │
                    ▼              ▼
                Postgres      Filesystem volume
                              (sha256-keyed images)
```

No Celery, no Redis, no external queue. Background extraction is an
in-process asyncio task pool gated by an `asyncio.Semaphore` whose
width is `EXTRACTION_CONCURRENCY` (default 3).

See [architecture-decisions.md §3, §4, §7](architecture-decisions.md)
for *why this shape*.

---

## Request lifecycle

A submission moves through six states:

```
   loaded ──▶ processing ──▶ ready_for_review ──▶ approved
                  │                  │
                  │                  └────────▶ rejected
                  ▼
           extraction_failed
                  │
                  └──▶ (re-run)  or  ──▶ approved / rejected
```

| State                | Set by                              | Means                                                |
| -------------------- | ----------------------------------- | ---------------------------------------------------- |
| `loaded`             | upload                              | Image + expected values stored, not yet extracted    |
| `processing`         | `POST /api/submissions/start`       | Vision call in flight                                |
| `ready_for_review`   | extractor finished cleanly          | Per-field verdicts ready for a reviewer              |
| `extraction_failed`  | extractor errored *or* boot rescue  | Reviewer can re-run or decide as-is                  |
| `approved`           | reviewer decision                   | Terminal — submission passes                         |
| `rejected`           | reviewer decision (with reasons)    | Terminal — submission fails                          |

State transitions are SQL `UPDATE`s on the `submissions` table; no
in-memory queue, so a container restart never loses state. Items left
in `processing` at startup are flipped to `extraction_failed` with
reason `"interrupted"` ([app/services/processor.py:104-114](../app/services/processor.py)).

### 1. Upload — single or batch

- **Single:** `POST /api/submissions` accepts one image + a JSON body
  of expected values.
- **Batch:** `POST /api/submissions/bulk` accepts up to 100 images +
  a CSV manifest (`filename, brand, class_type, alcohol_content,
  net_contents, producer_name, producer_address, is_imported,
  country_of_origin`). Each CSV row becomes one `loaded` submission;
  one bad row doesn't fail the whole batch.

Image type is verified by magic bytes (JPEG / PNG / WebP), not the
upload's content-type header
([app/api/submissions.py](../app/api/submissions.py)).

### 2. Start — reviewer clicks Run

`POST /api/submissions/start` flips all `loaded` submissions to
`processing` in a single SQL statement and dispatches a background
task per submission. The semaphore gates how many vision calls are
in flight at once; status is updated *before* the semaphore wait,
so the UI reflects "processing" immediately.

### 3. Extract — one vision call per label

[`pipeline/extract.py`](../pipeline/extract.py) sends the image to
OpenRouter with a Pydantic `LabelExtractionResponse` schema as the
structured-output target. The model returns:

- The eight expected-value fields (brand, class_type, alcohol_content,
  net_contents, producer_name, producer_address, is_imported,
  country_of_origin)
- `government_warning_text` — what the warning block says
- `government_warning_bold` — whether the "GOVERNMENT WARNING:" header
  is bold
- `government_warning_body_bold` — whether the warning body is bold
  (it should *not* be)
- Per-field `confidence` (high / medium / low)

Single call per label, not one call per field — see
[ADR §11](architecture-decisions.md).

### 4. Normalize — fold away cosmetic differences

[`pipeline/normalize.py`](../pipeline/normalize.py) applies
field-specific cleanup *before* comparison so that "Stone's Throw"
and "STONE'S THROW" never produce a mismatch on the basis of case
alone:

- Case-fold all text fields
- Collapse whitespace and strip punctuation
- Strip producer-role prefixes (`Imported by`, `Distilled and bottled by`)
- Expand state and country abbreviations (`KY → Kentucky`,
  `N.Y. → NY`)
- Convert net-contents units (`750 mL`, `750ML`, `0.75 L` all
  normalize the same way)

### 5. Compare — deterministic per-field rules

[`pipeline/compare.py`](../pipeline/compare.py) applies one rule per
field. Each verdict carries the rule it used, which is what the UI
shows under a mismatch.

| Field               | Rule                                                        |
| ------------------- | ----------------------------------------------------------- |
| `brand`             | Fuzzy match after normalize, threshold 85                   |
| `class_type`        | Fuzzy match after class-name normalize                      |
| `alcohol_content`   | Numeric ±0.1% absolute                                      |
| `net_contents`      | Unit-aware exact match                                      |
| `producer_name`     | Fuzzy match after producer-role normalize                   |
| `producer_address`  | Fuzzy match after state/country normalize                   |
| `is_imported`       | Boolean exact                                               |
| `country_of_origin` | Exact match after country normalize; nullable if domestic   |
| Government Warning  | Strict equality against the canonical 27 CFR 16.21 text     |
| Warning bold style  | Header bold + body *not* bold; only evaluated if text matches |

No LLM is asked to judge equivalence. See
[TRADEOFFS §4](TRADEOFFS.md) for the deterministic-vs-LLM-judge
discussion.

### 6. Review — human always decides

Submissions in `ready_for_review` show in the queue with per-field
verdicts. The reviewer can:

- **Open the image at full size** to verify manually.
- **Override any verdict** (pass → fail, fail → pass) with a comment.
  Overrides persist as their own rows in `field_overrides`, so the
  original model verdict is preserved alongside the human change.
- **Approve** the submission (terminal `approved`).
- **Reject** the submission with structured reasons (terminal
  `rejected`).

Submissions in `extraction_failed` are still reviewable — the
reviewer can re-run the extraction, decide as-is, or reject. See
[ADR §8](architecture-decisions.md).

---

## Failure modes and recovery

| Failure                                    | Recovery                                              |
| ------------------------------------------ | ----------------------------------------------------- |
| Vision call returns an error / times out   | Submission lands in `extraction_failed`; siblings unaffected |
| Container restarts mid-extraction          | Boot-time rescue flips `processing` → `extraction_failed` with reason `"interrupted"` |
| Reviewer disagrees with a model verdict    | Override with comment; model verdict preserved       |
| Reviewer needs to redo everything          | `POST /api/admin/reset` clears user data, re-seeds fixtures |
| Same image uploaded twice                  | Storage is sha256-keyed; the second upload reuses the existing file |

There is no automatic retry on the vision call. The reviewer's "Run"
button is the retry. See [TRADEOFFS §7](TRADEOFFS.md).

---

## Where to read next

- [Spec](../specs/001-verify-and-review/spec.md) — user stories and
  acceptance scenarios
- [Data model](../specs/001-verify-and-review/data-model.md) — full
  Postgres schema
- [API contract](../specs/001-verify-and-review/contracts/api.md) —
  endpoint shapes
- [Architecture decisions](architecture-decisions.md) — *why this
  shape*
- [Tradeoffs](TRADEOFFS.md) — what we gave up
- [Interview highlights](interview-highlights.md) — the stakeholder
  context behind the decisions

# Phase 1 Data Model: Verify-and-Review Workflow

SQLAlchemy 2.x ORM models living in `app/db/models.py`. All migrations are Alembic.
Identifiers are UUIDs (PostgreSQL `uuid` type) stored as `UUID` in SQLAlchemy. Timestamps
are `TIMESTAMP WITH TIME ZONE`, default `now()`.

Relationships are spelled out below; the goal is one row per concept, no clever
embedding, no premature denormalization.

---

## Canonical enums

### Submission status

The DB column and API payload always carry **machine values**. The frontend renders
**display labels** via a single mapping helper. No other strings appear in the codebase.

| Machine value         | Display label       |
|---|---|
| `loaded`              | Loaded              |
| `processing`          | Processing          |
| `ready_for_review`    | Ready for Review    |
| `approved`            | Approved            |
| `rejected`            | Rejected            |
| `extraction_failed`   | Extraction Failed   |

### Comparison verdict

`comparisons.verdict` is one of three machine values: `pass`, `fail`, `not_applicable`.
`field_overrides.override_verdict` is one of two: `pass`, `fail`. The reader-computed
**effective verdict** is the override's value if a `field_overrides` row exists,
otherwise `comparisons.verdict`. See [research.md R11](research.md) for how these
machine values map to UI states (including "Overridden" and "Needs Attention").

---

## Entities

### `submissions`

One row per item in the queue (fixture or user-added).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `image_key` | TEXT | NOT NULL | Storage key returned by `ImageStore.put`; never a path. |
| `expected_values` | JSONB | NOT NULL | The full expected-values record; see schema below. |
| `status` | TEXT | NOT NULL | Enum: `loaded` / `processing` / `ready_for_review` / `approved` / `rejected` / `extraction_failed`. |
| `is_fixture` | BOOLEAN | NOT NULL, default false | True for items seeded from `test_data/`. Reset preserves these. |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now | Touched on every status change. |

Indexes:
- `(status)` for queue filtering and the startup rescue scan.
- `(is_fixture, status)` to support `POST /admin/reset` cleanup queries.

State transitions:
- `loaded` → `processing` (on `POST /submissions/start`)
- `processing` → `ready_for_review` (on successful pipeline completion)
- `processing` → `extraction_failed` (on pipeline error)
- `ready_for_review` → `approved` | `rejected` (on `POST /submissions/{id}/decision`)
- `extraction_failed` → `approved` | `rejected` (reviewer can still decide via overrides)
- Reverse transitions are not allowed by the API.

**Validation rules** (applied at the API boundary in `app/api/schemas.py`):

`expected_values` is validated against this shape:

```json
{
  "brand": "string, required",
  "class_type": "string, required",
  "alcohol_content": "number, required",
  "net_contents": "string, required, e.g. '750 mL'",
  "producer_name": "string, required",
  "producer_address": "string, required",
  "is_imported": "boolean, required",
  "country_of_origin": "string, required iff is_imported=true; nullable otherwise"
}
```

Validation error: `is_imported=true && country_of_origin is null/empty` → 400.

---

### `extractions`

One row per submission, written when the processor finishes (success or failure).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `submission_id` | UUID | NOT NULL, FK → submissions.id, UNIQUE | One extraction per submission. |
| `extracted_label` | JSONB | NULL on failure | The `ExtractedLabel` Pydantic dump. |
| `field_confidence` | JSONB | NULL on failure | The `field_confidence` dict from the pipeline. |
| `latency_ms` | INTEGER | NULL on failure | |
| `input_tokens` | INTEGER | NULL on failure | |
| `output_tokens` | INTEGER | NULL on failure | |
| `model` | TEXT | NOT NULL | The model identifier used. Records drift over time. |
| `error` | TEXT | NULL on success | Stringified error if extraction failed. |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |

Index: `(submission_id)` (UNIQUE already).

---

### `comparisons`

One row per field per submission, populated when extraction succeeds.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `submission_id` | UUID | NOT NULL, FK → submissions.id | |
| `field` | TEXT | NOT NULL | Field key (e.g., `brand`, `government_warning_text`). |
| `verdict` | TEXT | NOT NULL | Enum: `pass` / `fail` / `not_applicable`. |
| `rule` | TEXT | NOT NULL | Human-readable rule label ("fuzzy match ≥85%", "numeric tolerance ±0.1%", "exact match"). |
| `extracted_value` | TEXT | NULL allowed | String representation; numeric/boolean rendered as text. |
| `expected_value` | TEXT | NULL allowed | Same. |
| `reason` | TEXT | NULL allowed | The `reason` string from `pipeline.compare`. |
| `diff_extracted` | JSONB | NULL allowed | Token list for failing text fields only (see Word-Diff Format below). |
| `diff_expected` | JSONB | NULL allowed | Same. |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |

Indexes:
- `(submission_id)` for joining when assembling the review payload.
- `(submission_id, field)` UNIQUE — exactly one comparison row per field per submission.

**Synthesized rows on extraction failure**: when extraction fails, the processor still
writes one comparison row per field — with `verdict='fail'` (or `'not_applicable'`
for fields irrelevant to this submission, e.g. `country_of_origin` on a domestic
label), `rule='extraction failed'`, `extracted_value=null`,
`expected_value` populated from `submissions.expected_values`, and `diff_*=null`. This
preserves the invariant that every submission past the `processing` state has a
complete `comparisons` set, which keeps the override and rejection APIs uniform. See
research R13 for the full rationale and UI implications.

**Field set**: the fixed list of fields the system compares:

| Group | Fields |
|---|---|
| Identity | `brand`, `class_type` |
| Producer | `producer_name`, `producer_address` |
| Quantitative | `alcohol_content`, `net_contents` |
| Origin | `is_imported`, `country_of_origin` |
| Government Warning | `government_warning_text`, `government_warning_style` |

`government_warning_style` is a synthetic field combining the two bold flags
(`government_warning_bold`, `government_warning_body_bold`) — UI sees one row, not two.

Word-diff format (only populated when `verdict='fail'` and the field is textual):

```json
[
  {"text": "Government", "kind": "equal"},
  {"text": " ",          "kind": "equal"},
  {"text": "WARNING",    "kind": "equal"},
  {"text": ":",          "kind": "equal"},
  {"text": " ",          "kind": "equal"},
  {"text": "According",  "kind": "added"},
  {"text": "Accord ing", "kind": "removed"}
]
```

`kind`: `equal` | `added` (present in extracted, not expected) | `removed` (present in
expected, not extracted). Whitespace tokens preserved so the UI can render contiguous
text.

---

### `field_overrides`

One row per overridden field. Optional — fields without an override have no row here.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `submission_id` | UUID | NOT NULL, FK → submissions.id | |
| `field` | TEXT | NOT NULL | Matches `comparisons.field`. |
| `original_verdict` | TEXT | NOT NULL | Snapshot of model verdict at time of override. |
| `override_verdict` | TEXT | NOT NULL | `pass` or `fail`. |
| `comment` | TEXT | NOT NULL | Short reviewer note (required per FR-019). |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |

Indexes:
- `(submission_id, field)` UNIQUE — one override per field; re-overriding overwrites
  (with an UPDATE that preserves the row's `id` and `created_at`? — NO, replace the row
  with a new one to maintain a simple history view; previous overrides are not kept,
  consistent with the spec's "current state survives reload" requirement, not "audit
  every override").
- Actually retained as UPSERT-style overwrite (DELETE old, INSERT new in same tx).

**Effective verdict** for a field is computed at read time:
- If a `field_overrides` row exists → its `override_verdict`.
- Else → `comparisons.verdict`.

The original model verdict is always visible in the UI (FR-020).

---

### `reviews`

The item-level decision. Exactly one row per submission once a decision is made.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `submission_id` | UUID | NOT NULL, FK → submissions.id, UNIQUE | |
| `decision` | TEXT | NOT NULL | Enum: `approved` / `rejected`. |
| `comment` | TEXT | NULL allowed | Free-text item-level comment. |
| `rejection_field_ids` | JSONB | NULL on approve, NOT NULL on reject | Array of `comparisons.id` selected as rejection reasons. Empty array forbidden on reject. |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |

Indexes:
- `(submission_id)` UNIQUE.

**Validation**:
- `decision='rejected'` && (`rejection_field_ids` is null or empty array) → 400.
- Submitting a `reviews` row also flips `submissions.status` to `approved` or `rejected`
  in the same transaction.

---

## Relationship diagram (textual)

```
submissions (1) ──── (1) extractions
            (1) ──── (0..N) comparisons      (exactly 10 rows per submission once
            (1) ──── (0..N) field_overrides   extraction succeeds — one per field)
            (1) ──── (0..1) reviews
```

---

## Read-model: the review payload

The endpoint `GET /api/submissions/{id}` returns a denormalized payload that the review
screen renders directly. The shape is precisely:

```json
{
  "id": "uuid",
  "status": "ready_for_review",
  "is_fixture": false,
  "created_at": "...",
  "image_url": "/api/submissions/{id}/image",
  "expected_values": { ... },
  "extraction": {
    "model": "google/gemini-3.1-pro-preview",
    "latency_ms": 2843,
    "tokens": {"input": 1207, "output": 218},
    "error": null
  },
  "groups": [
    {
      "name": "Identity",
      "fields": [
        {
          "field": "brand",
          "extracted": "Stone's Throw",
          "expected": "STONE'S THROW",
          "model_verdict": "pass",
          "effective_verdict": "pass",
          "rule": "fuzzy match ≥85%",
          "reason": "...",
          "confidence": "hi",          // "hi" | "med" | "low" | null — null for non-text fields
          "diff": null,
          "override": null
        }
      ]
    }
    // ... 4 more groups
  ],
  "review": null  // or {decision, comment, rejection_field_ids, created_at}
}
```

This is the only place where the data layout is reshaped for the UI; all writes hit
normalized tables.

---

## Index summary

For migration planning:
- `submissions.status`
- `submissions(is_fixture, status)`
- `extractions.submission_id` (UNIQUE, via FK constraint)
- `comparisons.submission_id`
- `comparisons(submission_id, field)` UNIQUE
- `field_overrides(submission_id, field)` UNIQUE
- `reviews.submission_id` UNIQUE

No full-text search, no GIN on JSONB, no triggers. Pure relational + JSONB columns where
the data is genuinely document-shaped (`expected_values`, `extracted_label`,
`field_confidence`, `diff_*`, `rejection_field_ids`).

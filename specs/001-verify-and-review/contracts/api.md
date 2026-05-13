# API Contract: Verify-and-Review

HTTP contract for the FastAPI backend. All endpoints are JSON unless otherwise noted.
Path prefix: `/api`. The frontend uses `openapi-typescript` to generate matching client
types from FastAPI's auto-generated schema; this document is the human-readable mirror
of that contract.

Authentication: none (prototype, single shared instance).

Error format (all 4xx/5xx):

```json
{
  "detail": "human-readable message",
  "code": "machine-readable short code (optional)"
}
```

---

## Health

### `GET /healthz`

Returns 200 OK with `{"status": "ok"}` when the app is alive and the DB is reachable.
500 otherwise. Used by Railway and any future Azure Container Apps probe.

---

## Queue

### `GET /api/submissions`

Lists every submission in compact form for the queue screen.

Response 200:

```json
[
  {
    "id": "uuid",
    "status": "loaded | processing | ready_for_review | approved | rejected | extraction_failed",
    "brand": "string from expected_values, used as display label",
    "is_fixture": true,
    "created_at": "iso8601",
    "thumbnail_url": "/api/submissions/{id}/image",
    "has_extraction_error": false
  }
]
```

Ordering: `created_at DESC`. No pagination in v1 (prototype scale).

---

### `POST /api/submissions`

Create one submission (image + expected values). The frontend's "Add to queue" action.

Request: `multipart/form-data`
- `image`: file (image/* content type, max 10 MB)
- `expected_values`: string (JSON document matching the schema in
  [data-model.md § submissions](../data-model.md))

Response 201:

```json
{ "id": "uuid", "status": "loaded" }
```

Errors:
- 400 with `detail` if image missing/oversize/wrong content type.
- 400 with `detail` if `expected_values` is not valid JSON or fails schema validation
  (e.g., `is_imported=true` && `country_of_origin` empty).
- 415 if `image` content type is not `image/*`.

---

### `POST /api/submissions/start`

Move every `loaded` submission to `processing` and schedule background extraction.
No request body.

Response 202:

```json
{
  "scheduled": 7,
  "submission_ids": ["uuid", "..."]
}
```

If zero items are in `loaded` state: 200 with `{"scheduled": 0, "submission_ids": []}`.

This endpoint returns immediately; clients poll `GET /api/submissions` to watch
transitions.

**Semantics** (see research R12 for the full analysis):
- All eligible items flip to `processing` in one transaction before the handler returns
  — items are never left visibly `loaded` while siblings start running.
- The configured concurrency limit (`EXTRACTION_CONCURRENCY`, default 3) throttles only
  the parallelism of the vision calls. The other items remain `processing` while
  waiting for a slot.
- Items transition to `ready_for_review` (or `extraction_failed`) individually, in the
  order their vision calls return — not as a block. The reviewer can open any item the
  moment it reports `ready_for_review`.

---

### `GET /api/submissions/{id}`

The review-screen payload. Full denormalized view.

Response 200: see [data-model.md § Read-model: the review payload](../data-model.md).
The per-field `confidence` is one of `"hi" | "med" | "low" | null`; non-text fields
(`is_imported`, `government_warning_style`) always carry `null` — see research R11.

Response 404 if id unknown.

Response 200 with `status: "loaded"` or `"processing"` returns the payload but the
`groups` array is empty and `extraction` is `null`. Review UI handles this by showing
a "still processing" placeholder rather than redirecting.

Response 200 with `status: "extraction_failed"` returns the **same envelope as a
successful submission**: `extraction.error` is a non-null string, and `groups`
contains all 5 groups with all 10 synthesized field rows
(`extracted_value: null`, `model_verdict: "fail"` or `"not_applicable"`,
`rule: "extraction failed"`, `confidence: null`, `diff: null`). The override and
decision endpoints accept these synthesized rows by ID exactly like normal rows. The
review UI surfaces a banner with the error and renders the rows in the normal layout
with the Extracted column showing a placeholder. See research R13.

---

### `GET /api/submissions/{id}/image`

Streams the source image (`image/jpeg` or `image/png`). 404 if id unknown.

---

## Field-level overrides

### `POST /api/submissions/{id}/overrides`

Apply or replace an override on a single field.

Request body:

```json
{
  "field": "brand",
  "override_verdict": "pass | fail",
  "comment": "non-empty string"
}
```

Response 200:

```json
{
  "field": "brand",
  "original_verdict": "fail",
  "override_verdict": "pass",
  "comment": "...",
  "created_at": "..."
}
```

Errors:
- 400 if `field` is not in the known field set or `comment` is empty.
- 409 if the submission's `status` is not `ready_for_review` or `extraction_failed`.

If a row already exists for `(submission_id, field)`, it is replaced (UPSERT semantics).

---

### `DELETE /api/submissions/{id}/overrides/{field}`

Remove an override; the comparison's model verdict becomes the effective verdict again.

Response 204 on success.
Response 404 if no override exists for that field.

---

## Item decision

### `POST /api/submissions/{id}/decision`

Submit the final approve/reject decision.

Request body:

```json
{
  "decision": "approved | rejected",
  "comment": "optional free-text",
  "rejection_field_ids": ["uuid", "..."]
}
```

- `comment` may be empty/omitted.
- `rejection_field_ids` is required and must be non-empty when
  `decision == "rejected"`. Each id must correspond to a `comparisons` row on this
  submission. The reviewer may cite any field — including ones the model
  marked `pass` — because the reviewer's judgment is authoritative.
- `rejection_field_ids` must be omitted or `[]` when `decision == "approved"`.

Response 200:

```json
{
  "decision": "rejected",
  "comment": "...",
  "rejection_field_ids": ["uuid"],
  "created_at": "..."
}
```

Side effect: `submissions.status` flips to `approved` or `rejected`.

Errors:
- 400 on validation (missing reasons on reject, reasons present on approve, comment too
  long > 2000 chars).
- 409 if a decision already exists for this submission (decisions are final; no edits in
  v1).
- 409 if `submissions.status` is not `ready_for_review` or `extraction_failed`.

Note: when approving a submission that still has failing fields after overrides, the
endpoint accepts the request. The "are you sure?" confirmation lives in the frontend
(see [research.md R11](../research.md)).

---

## Admin

### `POST /api/admin/reset`

Wipe user data and re-seed fixtures. Destructive — confirmation lives in the frontend.

Request body:

```json
{ "confirm": true }
```

Response 200:

```json
{
  "deleted_submissions": 3,
  "restored_fixtures": 7
}
```

Errors:
- 400 if `confirm` is not exactly `true`.

Behavior:
- DELETE all submissions where `is_fixture = false` (cascades to `extractions`,
  `comparisons`, `field_overrides`, `reviews`).
- For fixture submissions: reset `status` to `loaded`, delete associated `extractions`,
  `comparisons`, `field_overrides`, and `reviews` rows.
- Delete image storage keys for the user-added submissions; leave fixture keys in
  place.

---

## Operational notes

- All endpoints set CORS allowing the dev-server origin via `CORS_ALLOWED_ORIGINS`
  (comma-separated). Default in prod: empty (same-origin only, since SPA is served
  from FastAPI).
- All write endpoints reject `Content-Type` other than `application/json` (or
  `multipart/form-data` for `POST /api/submissions`).
- Response headers always include `Cache-Control: no-store` for `/api/*`.

---

## What is intentionally NOT in the contract

- No SSE / WebSocket. Status update is polling only.
- No batch-approve / batch-reject. One decision per submission per request.
- No edit-decision endpoint. Decisions are final in v1 (audit story is "what the
  reviewer said the first time").
- No user/auth endpoints.
- No metrics endpoint beyond `/healthz`. Latency/cost is logged per extraction into the
  DB (`extractions` table) for future querying.

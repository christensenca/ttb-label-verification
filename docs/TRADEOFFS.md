# Tradeoffs and Limitations

This is a prototype, and several choices were sized for that. This doc
spells out what we deliberately gave up, why it was the right call for a
take-home, and what production would look like if this graduated into a
real tool.

Companion to [architecture-decisions.md](architecture-decisions.md) —
that doc records *what we chose*; this one records *what we gave up*.

---

## 1. Distilled-spirits-focused test corpus

**Decision.** All seven preloaded fixtures and the benchmarks in
[`reports/`](../reports) are distilled spirits (tequila, gin, bourbon,
rye, vodka). No beer or wine.

**What we gave up.** Empirical confidence on beer and wine categories.
Wine label conventions in particular (vintage, varietal, appellation,
class/type rules under 27 CFR Part 4) get richer than what spirits
exercise.

**Why this was right.** TTB's seven core required fields — brand,
class/type, ABV, net contents, producer name/address, country of origin
on imports, and the Government Warning — are shared across beer, wine,
and spirits per 27 CFR Parts 4, 5, and 7. The data model in
[`pipeline/extract.py`](../pipeline/extract.py) is built around those
seven fields plus warning text and bold style, so the *schema*
generalizes even though the *corpus* doesn't. Sarah's interview framed
the workflow in identical terms regardless of beverage type.

**Production.** Expand the eval corpus to ~10 fixtures per category and
add wine-specific field rules (vintage tolerance, appellation
normalization). The benchmark harness in
[`scripts/bench_models.py`](../scripts/bench_models.py) already
supports adding rows without touching pipeline code.

---

## 2. No authentication, no roles

**Decision.** Single shared demo URL. No login. No submitter / reviewer
separation. A banner on the page warns "shared demo instance — data is
visible to anyone with the link."

**What we gave up.** Audit trail by user. Any visitor can override a
verdict or approve/reject a submission, and the persisted decision
records carry only a comment, not an identity. In a real review
workflow there are at minimum two roles — *submitter* (uploads label +
expected values) and *reviewer* (approves or rejects) — and you want
each decision tied to a person for compliance defensibility.

**Why this was right.** Marcus's interview explicitly carved out
auth/PII concerns for the prototype ("just don't do anything crazy,
we're not storing anything sensitive for this exercise"). Adding
auth + roles is a non-trivial slice — login UI, session management, an
admin model — that competes with the core review experience for
attention. The reviewer override flow is in the right shape to absorb
user identity later: the `reviews` and `overrides` tables already
record per-decision rows with timestamp and comment.

**Production.** Three roles (submitter, reviewer, admin), SSO via
the federal identity provider, per-decision user attribution, and
lock-down on `POST /api/admin/reset`.

---

## 3. Higher-accuracy model with longer tail latency

**Decision.** Default to `google/gemini-3.1-pro-preview`
([`app/config.py:39`](../app/config.py),
[`pipeline/extract.py:30`](../pipeline/extract.py)).

**What we gave up.** ~2.4 seconds of mean latency vs. the fastest
viable alternative, and a higher per-call cost. The Pro model averages
**5.8 s** in our benchmark — slightly *over* Sarah's stated 5-second
ceiling.

**Why this was right.** Jenny's interview was specific: the Government
Warning has to be exact, word-for-word, all-caps, and bold — and people
try to slip non-compliant warnings past reviewers. Across the ten
models we benchmarked
([`reports/bench-20260513-153639.md`](../reports/bench-20260513-153639.md)):

| Model                        | Overall acc. | Warning text | Warning bold | Mean latency |
| ---------------------------- | ------------ | ------------ | ------------ | ------------ |
| **gemini-3.1-pro-preview**   | **95%**      | **100%**     | 57%          | **5783 ms**  |
| gemini-3.1-flash-lite        | 91%          | 86%          | 86%          | 3430 ms      |
| gemini-2.5-flash-lite        | 88%          | 43%          | 0%           | 2675 ms      |
| gpt-4o                       | 86%          | 86%          | 71%          | 5748 ms      |
| gemini-2.5-pro               | 91%          | 100%         | 43%          | 14073 ms     |

The Pro model wins on the field the regulation cares most about
(warning text) and on overall accuracy. The 0.8 s over Sarah's 5 s
ceiling is real and worth flagging.

**Mitigation today.** `OPENROUTER_MODEL` is an env var — operators can
swap in `gemini-3.1-flash-lite` (3.4 s, 91% / 86% / 86%) for a
latency-first deployment without touching code.

**Production.** Two paths worth considering: (a) a routed setup where
fast model handles the easy fields and Pro is reserved for the warning
block, or (b) cache + batch the vision call so the user-visible time is
bounded even when the upstream model is slow. Either way, the model
boundary is one function in
[`pipeline/extract.py`](../pipeline/extract.py).

---

## 4. Deterministic field comparison (no LLM-as-judge)

**Decision.** Vision-extracted fields are normalized in
[`pipeline/normalize.py`](../pipeline/normalize.py) — case folding,
whitespace collapsing, unit conversion, producer-role stripping,
state/country aliasing — and then compared with field-specific rules
in [`pipeline/compare.py`](../pipeline/compare.py) (fuzzy match
threshold for text fields, ±0.1% tolerance for ABV, unit-aware match
for net contents). No LLM is asked to judge whether two values are
"the same."

**What we gave up.** A judge LLM could absorb edge cases the
normalization layer hasn't been taught yet — e.g., new abbreviation
forms, unusual punctuation, semantic equivalences like
"Distillery No. 209" vs "No. 209 Distillery." Today those produce a
false mismatch until a normalization rule is added, and the reviewer
override is the escape hatch.

**Why this was right.** Deterministic compare is **fast**
(sub-millisecond), **free**, **debuggable** (each verdict carries the
specific rule applied — visible in the benchmark output and the UI),
and **stable across runs**. LLM-judge layers add per-field latency,
per-field cost, and a second source of model drift on top of the
extraction call. Dave's "STONE'S THROW" vs "Stone's Throw" case is
already handled by normalize + fuzzy match without an LLM in the loop.

**Production.** Hybrid is the right shape: keep deterministic compare
as the primary, and route only *low-confidence* verdicts (e.g., fuzzy
score in the 70-85 range, or extractor `confidence` of "low") through
a judge LLM. That way the cost/latency hit is paid only on the cases
that need it. The extractor already emits per-field confidence in the
Pydantic schema, so the routing signal is in place.

---

## 5. In-process asyncio task pool (no Celery / Redis / external queue)

**Decision.** Background extraction runs as in-process asyncio tasks
gated by an `asyncio.Semaphore` whose width is configured via
`EXTRACTION_CONCURRENCY` ([`app/services/processor.py:85-92`](../app/services/processor.py)).
No external broker.

**What we gave up.** Horizontal scaling and crash-durability. If the
container restarts mid-extraction, in-flight items are lost; on boot,
anything still in `processing` status is moved to `extraction_failed`
with reason `"interrupted"` and the reviewer can re-run it.

**Why this was right.** A single FastAPI container with an in-process
semaphore is the simplest possible topology that satisfies the
batch-of-300 scenario at prototype scale, and it deploys to Railway /
Azure Container Apps as a single artifact with no broker to manage.
Sarah's worst case is ~300 labels per importer dump — well within what
one container with `EXTRACTION_CONCURRENCY=3` can clear in a few
minutes.

**Production.** Migrate the background pool to Celery on Redis (or
Azure Service Bus). The boundary is `_run_in_background()` in
[`app/services/processor.py`](../app/services/processor.py); the
SQL-state lifecycle (`loaded → processing → ready_for_review →
extraction_failed`) doesn't change.

---

## 6. Local filesystem image storage

**Decision.** Images are written sha256-keyed to the directory in
`IMAGE_STORAGE_DIR` via an `ImageStore` Protocol
([`app/services/storage.py`](../app/services/storage.py)). Railway
provides a mounted volume; Docker users mount `-v $PWD/.local/images`.

**What we gave up.** The instance is coupled to its volume — if the
container migrates hosts the volume needs to migrate with it, and
multi-instance horizontal scale would require a shared filesystem.

**Why this was right.** Marcus's "no PII" guardrail removes the
business case for cloud-blob signed URLs / access controls at this
stage, and a content-addressed filesystem store gives the same
deduplication and stable URLs as a blob store with one fewer SDK in
the dependency tree. The `ImageStore` Protocol means the swap is
isolated.

**Production.** Azure Blob in an IL5/FedRAMP-authorized region. One
class to write
([`app/services/storage.py`](../app/services/storage.py)); the API
surface and the rest of the app don't change.

---

## 7. Bounded retry on transient errors; no Retry-After / circuit breaker yet

**Decision.** Transient OpenRouter errors (`APITimeoutError`,
`APIConnectionError`, `RateLimitError` / 429, `InternalServerError` / 5xx)
are retried with bounded exponential backoff + jitter — 3 retries, 1s→8s
base, ≤25% jitter — and an explicit 30s per-attempt timeout
([`pipeline/extract.py`](../pipeline/extract.py) `_call_with_retries`).
A 5-minute per-task wall-clock timeout in
[`app/services/processor.py`](../app/services/processor.py)
(`_run_with_timeout`) catches anything that retries can't, with a status
guard so the late-completing extractor thread can't overwrite the
watchdog's failure write. Boot-time rescue writes the full failure-shaped
record, not just a status flip.

**What we still gave up.** Three production-grade refinements:

- **`Retry-After` header.** Providers (including OpenRouter) sometimes
  send `Retry-After` on 429s with the exact recommended wait. We use our
  own backoff math instead, which is correct in expectation but slightly
  worse on tail latency during a real rate-limit incident.
- **Env-configurable retry budgets.** `_MAX_RETRIES`, the timeout, and
  the backoff bounds are module-level constants in `pipeline/extract.py`.
  Promoting them to settings would let ops tune per environment without a
  code change.
- **Circuit breaker.** Right now if OpenRouter is fully down, every
  submission burns ~130s of attempts before failing. A per-extractor
  circuit breaker would short-circuit subsequent calls during an outage,
  catching up faster once upstream recovers.

**Why this was right.** The implemented retry/timeout coverage absorbs
the routine class of transient errors that turned every traffic spike
into a manual-recovery wave under the previous "one attempt, then fail"
model. The three refinements above are real but second-order — each one
matters more once you're handling sustained traffic and tracking SLOs,
neither of which a prototype faces. They sit cleanly on top of the
current code; the boundary is the `_call_with_retries` helper.

**Production.** Add `Retry-After` parsing to the retry helper; promote
the four constants to `app/config.py`; add a circuit-breaker wrapper
around `pipeline.extract.extract` keyed on the extractor identity.

---

## 8. Image-only input (no PDF)

**Decision.** Accept JPEG, PNG, WebP only; reject everything else with
HTTP 415 ([`app/api/submissions.py`](../app/api/submissions.py)). Magic
bytes are checked rather than trusting the upload's content-type.

**What we gave up.** Real COLA submissions often arrive as PDFs (the
form *plus* the label artwork). A reviewer using this tool against
production COLA workflow would have to export the label page to an
image first.

**Why this was right.** The assignment frames the input as a "label
image," and the seven preloaded fixtures and benchmarks reflect that.
Adding a PDF page-extraction step (pdf2image / Poppler in the
container) is a real piece of work — image conversion, page selection
UI for multi-page PDFs, font/typography preservation for the bold
check — that doesn't move the needle on the core verification
question.

**Production.** PDF intake pipeline: detect PDF, render label page(s)
to PNG at print resolution, pass through the existing extractor.

---

## 9. Batch upload caps at 100 images / 200 MB

**Decision.** `POST /api/submissions/bulk` accepts up to 100 image
files and 200 MB total ([`app/api/submissions.py`](../app/api/submissions.py),
[`app/api/schemas.py`](../app/api/schemas.py)).

**What we gave up.** Sarah explicitly cited 200-300 label dumps from
peak-season importers. Today an importer with 300 labels would have to
split into three uploads.

**Why this was right.** A 100/200MB cap fits comfortably in a single
HTTP multipart upload without streaming concerns, and gives us a known
worst-case memory footprint at upload time. Bumping the cap is a
config change in [`app/api/schemas.py`](../app/api/schemas.py); the
processing pipeline downstream already paces itself with the
extraction semaphore regardless of batch size.

**Production.** Streaming or chunked uploads, plus a UI affordance for
resumable batches.

---

## 10. OpenRouter as the model boundary

**Decision.** All vision calls go through OpenRouter
([`pipeline/extract.py`](../pipeline/extract.py)).

**What we gave up.** Marcus's interview noted that TTB's network blocks
outbound traffic to a lot of vendor ML endpoints; their pilot with a
scanning vendor lost features for exactly this reason. OpenRouter would
likely be in that bucket.

**Why this was right.** For a prototype on a public-cloud demo URL,
OpenRouter buys us model portability with one config knob —
`OPENROUTER_MODEL` switches between Gemini, GPT, Claude, etc. without
touching code — and the benchmarks in [`reports/`](../reports) only
exist because of that portability.

**Production.** Swap to Azure OpenAI in the FedRAMP-authorized region
TTB already uses. The model boundary is one function call in
[`pipeline/extract.py`](../pipeline/extract.py); the rest of the
pipeline doesn't know what's behind it.

---

## 11. No formal audit log, retention policy, or FedRAMP posture

**Decision.** Reviewer decisions, overrides, and approve/reject
reasons are persisted in Postgres
([`app/models.py`](../app/models.py)), but there is no separate
append-only audit log, no document-retention enforcement, and no
FedRAMP/IL5 hardening.

**What we gave up.** Defensibility under a real compliance audit.
Today, the decision / review / override tables in
[`app/db/models.py`](../app/db/models.py) are a soft audit trail — you
can see *what* a verdict became and *what comment* was attached, but
rows are mutable and there's no hash-chained tamper-evident log.

**Why this was right.** Marcus explicitly said federal compliance was
out of scope for the prototype. The shape of the data model — every
state transition produces a new row with a timestamp, comment, and
(future) user — is the foundation an append-only audit log would sit
on top of.

**Production.** Append-only `audit_events` table, document retention
schedule wired to the existing storage interface (so retention applies
to images too), and a FedRAMP-aligned deployment topology (private VPC,
managed Postgres, KMS-encrypted blob, OpenAI on Azure).

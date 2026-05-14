# Architecture Decisions

Decisions captured from the planning conversation. Builds on [interview-highlights.md](interview-highlights.md). Open questions at the bottom.

## 1. Input model — label image + expected-values form

**Decision:** The app accepts a label image *plus* a form/JSON of expected values (brand, class/type, ABV, net contents, etc.). The system extracts fields from the label, compares against the expected values, and returns per-field pass/fail with evidence.

**Why:** Mirrors the workflow Sarah described — "does what's on the label match what's in the application?" Anything less (label-only extraction, or AI compliance check without comparison) demonstrates a feature rather than the actual job.

**Implications for the API contract:**
- Underlying request shape:
  ```
  {
    image,
    expected: {
      brand,
      class_type,
      alcohol_content,        // numeric ABV %
      net_contents,           // e.g. "750 mL"
      producer_name,
      producer_address,
      is_imported,            // bool — true requires country_of_origin
      country_of_origin       // required iff is_imported, else nullable
    }
  }
  ```
- Government Warning is always required for alcohol — not part of expected values, validated separately against the canonical text (see decision #6).
- A label-only "self-check" mode (does this label have all required fields, is the warning valid?) becomes a one-flag variation later.
- Batch falls out naturally — one expected-values record per label.

**Ruled out:**
- *Label image only* — doesn't match the workflow.
- *Label image + application PDF/image* — doubles OCR surface; real COLA applications are structured forms, not images.
- *Label only + compliance check* — useful as a secondary mode, not the core.

---

## 2. Extraction — OpenAI vision via OpenRouter

**Decision:** Vision LLM, single structured-output call per label. OpenAI models accessed through OpenRouter in both dev and production — same API surface end-to-end, no environment swap.

**Why:** Vision LLMs handle stylized brand fonts, ornate label layouts, and semantic field identification ("this block is the warning statement") in one call. Pure OCR (Tesseract) collapses on stylized fonts; cloud OCR (Textract, Vision) is tuned for receipts/forms, not labels. OpenRouter gives us model portability — `gpt-4o`, `claude`, `gemini` all behind one API, swap with one env var if we want to compare.

**Latency budget:** Sarah's hard cutoff is 5 seconds end-to-end. Vision call is the long pole at ~2–4s. OpenRouter adds ~100–300ms of proxy latency — acceptable inside the budget. The model itself is swappable via `OPENROUTER_MODEL` (config-only, no code change); the OpenRouter base URL is hard-coded in [pipeline/extract.py](../pipeline/extract.py) and would graduate to an env var if/when we move to Azure OpenAI.

**Government Warning gets a dedicated path.** Per Jenny, the warning has to be exact word-for-word, all-caps, bold. Strict matching, not LLM-as-judge. Open question on whether that's a second vision call or a post-extraction validation of the warning block — see below.

**Ruled out:**
- *Pure OCR + rules* — brittle on stylized labels; the future-firewall story is real but solving it isn't a prototype concern.
- *Cloud OCR alone* — wrong tool for labels.
- *Hybrid (cloud OCR + LLM)* — kept as a fallback if vision LLM latency is unworkable.

---

## 3. App framework — FastAPI + React/Vite

**Decision:** Python FastAPI backend, React + Vite frontend.

**Why:** Python is the lingua franca for vision/OCR libraries if we ever drop down from the LLM (Tesseract, Pillow, OpenCV, structured-output parsing). FastAPI's automatic OpenAPI schema gives us a typed contract between front and back essentially for free. Vite gives fast iteration on the React side.

**Trade-off vs. Next.js full-stack:** Next.js would be marginally faster to ship as one repo on Vercel, but you'd be writing the LLM-calling code in Node, and pivoting to OCR libraries later would mean a rewrite. FastAPI keeps the door open.

---

## 4. Deployment — container-first, Railway for the demo, Azure-portable

**Decision:** Multi-stage `Dockerfile` at the repo root. Deploy to Railway for the live demo URL. Same container drops into Azure Container Apps with one command — documented in the README.

**Why:**
- Railway is the lowest-friction container host that still gives a portable artifact. The user already has a Railway workflow.
- Marcus said TTB runs on Azure but doesn't require the *prototype* to. Container-first satisfies both: ship fast, demonstrate Azure-readiness.
- Same Dockerfile → `az containerapp up --name ttb-verify --source .` for a future Azure deploy.

**Setup:**
- Multi-stage Dockerfile: build the Vite bundle in a Node stage, copy `dist/` into the FastAPI image, serve static assets from FastAPI so there's one container/one port.
- `/healthz` endpoint for Railway's restart logic.
- Environment variables (not committed): `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `DATABASE_URL`, `IMAGE_STORAGE_DIR`. See [.env.example](../.env.example).

**Trade-off acknowledged:** Railway has no free tier — $5/mo Hobby plan or trial credits.

**Ruled out:**
- *Direct Azure App Service deploy* — too much config friction for a weekend prototype.
- *Vercel / Render / Fly* — equivalent to Railway functionally, but Railway is the existing-workflow choice.

---

## 5. Request shape — async submission queue, polled by the UI

**Decision:** All submissions land asynchronously. Upload returns immediately with a `loaded` row; a separate Run step starts background extraction; the UI polls submission status until each row reaches `ready_for_review` or `extraction_failed`.

| Endpoint | Shape | Use case |
|---|---|---|
| `POST /api/submissions` | Sync upload, returns submission row in `loaded` status | Single label |
| `POST /api/submissions/bulk` | Sync upload, returns N rows in `loaded` status | CSV manifest + image files (≤100 / 200 MB) |
| `POST /api/submissions/start` | Flips all `loaded` rows to `processing`, schedules background extraction | Reviewer's "Run" button |
| `GET /api/submissions` / `GET /api/submissions/{id}` | Read the queue / one row | UI polling; reviewers open rows once `ready_for_review` |

**Why:** Sync extraction at upload time breaks at batch (no holding an HTTP connection for 25 minutes) and would couple upload latency to the model's worst-case response time. Splitting upload from "Run" gives the reviewer a chance to load a batch, glance at it, and start extraction deliberately. The single async surface is two endpoints (`/submissions` for write, `/submissions/{id}` for read) and the UI polls — simpler than a sync-vs-async split.

---

## 6. Comparison strategy — per-field strictness

**Decision:** Programmatic comparison with field-specific rules. No LLM-as-judge for comparison.

| Field | Rule |
|---|---|
| Government Warning | Strict — exact text, all-caps, bold required. Surface specifically what failed. Always required for alcohol — not part of expected values, validated against the canonical text. |
| `brand`, `class_type`, `producer_name` | Normalize (case, whitespace, punctuation), then fuzzy match (Levenshtein or similar) with threshold. Handles Dave's `STONE'S THROW` vs `Stone's Throw`. |
| `producer_address` | Normalize then fuzzy match — accept abbreviations (`Kentucky` ≡ `KY`). |
| `alcohol_content` | Numeric tolerance (e.g., ±0.1%) — labels vary in display precision. |
| `net_contents` | Unit-aware (`750 mL` ≡ `750ML` ≡ `0.75L`). |
| `is_imported` | Boolean exact match. If true, `country_of_origin` is required on both sides. |
| `country_of_origin` | Normalized exact match. Required iff `is_imported`; if domestic, missing on label is acceptable. |

**Why:** Programmatic comparison is fast (sub-millisecond), free, explainable to the agent ("brand differed only in case — passed under fuzzy match rule"), and not subject to model drift. LLM-as-judge is slow, expensive, and harder to trust.

---

## 7. Image storage — Railway volume, content-addressed paths

**Decision:** Uploaded images written to a Railway-mounted volume (path read from `IMAGE_STORAGE_DIR`, e.g. `/data/images`), under content-addressed filenames so the result view can render the image alongside the verification result. Wrapped behind a small storage interface so swapping to Azure Blob / S3 is small and isolated if the deploy target ever changes.

**Why:** Railway volumes give us durability — images persist across container restarts and redeploys — without standing up a separate blob service. Matches the single-container scale of the prototype. Marcus said no PII concerns for the exercise, so we don't need the access-control / signed-URL machinery blob storage would bring.

**Setup:**
- Volume mounted at the path in `IMAGE_STORAGE_DIR`.
- Fixture images (decision #9) ship in the container build; the seed step copies them onto the volume on first boot if missing.
- `POST /admin/reset` clears user-added images and re-copies fixtures.

**Trade-off:** Volume mounts are single-container — fine for the prototype, but if we ever scale horizontally we'd switch to blob. That's why the storage interface stays.

**Ruled out:**
- *Container-local ephemeral disk* — wipes on restart, would orphan `image_path` rows in Postgres.
- *Azure Blob / S3 now* — overkill for current scale; adds SDK + auth + signed-URL plumbing not worth it yet.

---

## 8. Human-in-the-loop review — model proposes, human decides

**Decision:** The verification pipeline never auto-accepts. Every submitted label produces a pending-review item; a human reviewer approves or rejects each field individually before the item is considered verified. Submission is decoupled from review.

**Why:** Sarah's job and Jenny's compliance posture both require human accountability on TTB submissions. An AI-only pass/fail is a liability, not a feature. Treating the model as a first-pass annotator with a human approver makes the tool trustworthy and matches the actual workflow — the model observes and reports, the human decides.

**Flow:**
1. User submits one or more labels (image + expected values) via single or batch endpoints.
2. Pipeline runs extraction + comparison, produces per-field pass/fail with evidence.
3. Item lands in a review queue with status `pending_review`.
4. Reviewer opens the item, sees the label image alongside model output and comparison verdicts.
5. Reviewer approves/rejects each field (or the whole item), optionally with notes.
6. Final status is recorded — both model output and human decisions persist for audit.

**Implications:**
- Batch upload (decision #5) creates N queue items, not N synchronous decisions.
- Sync `/verify` still returns the model's result inline so the UI can show it immediately, but the item also lands in the queue.
- This is what forces a database — see decision #9.

---

## 9. Database — Postgres via SQLAlchemy + Alembic

**Decision:** PostgreSQL, accessed via SQLAlchemy 2.x with Alembic migrations. Hosted as a Railway Postgres add-on for the demo; portable to Azure Database for PostgreSQL with no code change.

**Why:** The review queue (decision #8) requires persistence across sessions, which settles the "do we need a DB" question. Postgres over SQLite for stability — same effort with SQLAlchemy in front, and we avoid the SQLite→Postgres swap later. The portability discipline (ORM only, no raw SQL, `DATABASE_URL` everywhere) keeps the door open to Azure with zero code change.

**Schema sketch (subject to change):**
- `submissions` — one row per uploaded label: id, image_path, expected_values (JSONB), status, submitted_at.
- `extractions` — model output per submission: extracted fields, raw response, model version, latency, cost.
- `comparisons` — per-field pass/fail with evidence and rule applied.
- `reviews` — human decisions: per-field approve/reject, notes, decided_at.

**Single-user prototype framing:**
- No auth. The deployed instance is a shared demo; UI shows a "shared demo instance — data is visible to anyone with the link" banner.
- Preloaded fixtures: a handful of submissions in various states (pending, approved, rejected) so a fresh visitor can explore the review UX without uploading anything. Fixture images ship inside the container build.
- `POST /admin/reset` endpoint — wipes user-added data and re-seeds fixtures. Surfaced in the UI as a reset button.

**Portability discipline:**
- All DB access through SQLAlchemy ORM — no raw SQL strings.
- Alembic for schema changes from day one.
- `DATABASE_URL` env var (Railway provides, Azure provides) — no hardcoded connection logic.
- Avoid Postgres-only features (arrays, full-text search) unless we explicitly decide we want them.

**Ruled out:**
- *SQLite* — would work, but the migration to Postgres later is non-zero even with SQLAlchemy in front. Choosing Postgres now removes the swap.
- *No DB* — incompatible with the review queue.

---

## 10. Extraction output mode — structured outputs with Pydantic schema

**Decision:** Use the OpenAI structured-output API (`client.beta.chat.completions.parse` with `response_format=<PydanticModel>`). The `LabelExtractionResponse` Pydantic model in [pipeline/extract.py](../pipeline/extract.py) defines every field; the server enforces the schema and returns a parsed object.

**Why:** Eliminates a whole class of parse failures. Free-form text + regex is fragile across model versions. The older JSON mode (`response_format={"type": "json_object"}`) gives JSON but no schema enforcement — still requires defensive parsing. Structured outputs are the most drift-resistant option and the schema lives in code, type-checked.

**Trade-off:** Tied to providers that implement OpenAI's structured-output API. OpenRouter routes it transparently for supporting models. If we ever pick a model that doesn't, we fall back to JSON mode + Pydantic validation post-parse.

---

## 11. Vision call topology — one call, post-hoc warning validation

**Decision:** A single vision call per label extracts everything — brand, class/type, ABV, producer info, etc., *and* the Government Warning text plus its bold/style flags. Strict warning validation (decision #6) runs in the comparison layer against the extracted text + flags, not in a separate vision call.

**Why:** Two calls would double latency for a marginal accuracy gain. The warning's strictness can be enforced post-extraction with normalized string matching against the canonical 27 CFR 16.21 text — the model only needs to report what it sees, not judge it. Bold/style detection is a model job; correctness checking is a programmatic job.

**Implications:**
- The Pydantic schema includes `government_warning_text`, `government_warning_bold`, and `government_warning_body_bold`.
- The 5-second end-to-end latency budget (decision #2) stays achievable on one call.

**Ruled out:**
- *Second vision call dedicated to the warning* — kept as a fallback if benchmarks show warning extraction is unreliable, but current benchmarks don't justify it.

---

## Deferred decisions

- **Agent input form shape.** Field-by-field form vs. JSON paste. Leaning JSON-based given the "JSON + images" framing of submissions, but the UI affordance is undecided.
- **Batch upload UX.** Multiple image uploads + a single JSON document of expected values, vs. one zip bundle, vs. per-row API calls. Affects the batch endpoint shape directly.

---

## Stack summary

| Layer | Choice |
|---|---|
| Frontend | React + Vite |
| Backend | FastAPI (Python) |
| Vision | Vision LLM via OpenRouter (model configurable; current default Gemini) |
| Extraction output | OpenAI structured outputs, Pydantic schema enforced |
| Vision call topology | Single call per label, post-hoc warning validation |
| Comparison | Programmatic, per-field strictness |
| Review | Human-in-the-loop, per-field approve/reject; model never auto-accepts |
| Storage (images) | Railway volume (`IMAGE_STORAGE_DIR`); fixtures baked into container, copied to volume on first boot |
| Database | Postgres (Railway Postgres add-on, SQLAlchemy + Alembic) |
| Container | Multi-stage Dockerfile |
| Host | Railway (Azure Container Apps portable) |

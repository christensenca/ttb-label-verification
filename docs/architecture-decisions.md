# Architecture Decisions

Decisions captured from the planning conversation. Builds on [interview-highlights.md](interview-highlights.md). Open questions at the bottom.

## 1. Input model — label image + expected-values form

**Decision:** The app accepts a label image *plus* a form/JSON of expected values (brand, class/type, ABV, net contents, etc.). The system extracts fields from the label, compares against the expected values, and returns per-field pass/fail with evidence.

**Why:** Mirrors the workflow Sarah described — "does what's on the label match what's in the application?" Anything less (label-only extraction, or AI compliance check without comparison) demonstrates a feature rather than the actual job.

**Implications for the API contract:**
- Underlying request shape: `{ image, expected: { brand, class_type, abv, net_contents, producer, country_of_origin, warning_required: true } }`
- A label-only "self-check" mode (does this label have all required fields, is the warning valid?) becomes a one-flag variation later.
- Batch falls out naturally — one expected-values record per label.

**Ruled out:**
- *Label image only* — doesn't match the workflow.
- *Label image + application PDF/image* — doubles OCR surface; real COLA applications are structured forms, not images.
- *Label only + compliance check* — useful as a secondary mode, not the core.

---

## 2. Extraction — OpenAI vision via OpenRouter (swap to direct OpenAI for demo)

**Decision:** Vision LLM, single structured-output call per label. OpenAI through OpenRouter during development; benchmark against direct OpenAI before the demo and swap if latency requires it.

**Why:** Vision LLMs handle stylized brand fonts, ornate label layouts, and semantic field identification ("this block is the warning statement") in one call. Pure OCR (Tesseract) collapses on stylized fonts; cloud OCR (Textract, Vision) is tuned for receipts/forms, not labels.

**Latency budget caveat:** Sarah's hard cutoff is 5 seconds end-to-end. Vision call is the long pole at ~2–4s. OpenRouter adds ~100–300ms of proxy latency — small but non-trivial against that budget. Swap path:

```python
# Single env-var change between OpenRouter and direct OpenAI
OPENAI_BASE_URL=https://openrouter.ai/api/v1  # dev
OPENAI_BASE_URL=https://api.openai.com/v1     # demo
```

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
- Environment variables (not committed): `OPENAI_API_KEY`, `OPENAI_BASE_URL`.

**Trade-off acknowledged:** Railway has no free tier — $5/mo Hobby plan or trial credits.

**Ruled out:**
- *Direct Azure App Service deploy* — too much config friction for a weekend prototype.
- *Vercel / Render / Fly* — equivalent to Railway functionally, but Railway is the existing-workflow choice.

---

## 5. Request shape — sync for single, async for batch

**Decision:** Mixed mode.

| Endpoint | Shape | Use case |
|---|---|---|
| `POST /verify` | Sync, returns result inline in <5s | Single label, agent waits |
| `POST /verify/batch` | Async, returns job ID; `GET /verify/batch/{id}` polls status | 200–300 labels from a single importer |

**Why:** Sync everywhere breaks at batch (no holding an HTTP connection for 25 minutes). Async everywhere makes single-label feel slow and adds polling/SSE complexity for the common case. Mixed is two code paths but each is simple.

---

## 6. Comparison strategy — per-field strictness

**Decision:** Programmatic comparison with field-specific rules. No LLM-as-judge for comparison.

| Field | Rule |
|---|---|
| Government Warning | Strict — exact text, all-caps, bold required. Surface specifically what failed. |
| Brand name, producer, class/type | Normalize (case, whitespace, punctuation), then fuzzy match (Levenshtein or similar) with threshold. Handles Dave's `STONE'S THROW` vs `Stone's Throw`. |
| ABV | Numeric tolerance (e.g., ±0.1%) — labels vary in display precision. |
| Net contents | Unit-aware (`750 mL` ≡ `750ML` ≡ `0.75L`). |
| Country of origin | Normalized exact match. |

**Why:** Programmatic comparison is fast (sub-millisecond), free, explainable to the agent ("brand differed only in case — passed under fuzzy match rule"), and not subject to model drift. LLM-as-judge is slow, expensive, and harder to trust.

---

## 7. Image storage — local disk for prototype, swap-ready

**Decision:** Uploaded images written to local disk in the container during the request. Stored under a content-addressed path so the result view can render the image alongside the verification result. Wrapped behind a small storage interface so swapping to Azure Blob / S3 is ~20 lines.

**Why:** Prototype scope. Marcus said no PII concerns for the exercise. Local disk + SQLite (if/when we add a DB) is a coherent "ephemeral prototype" story. Container restart wipes the directory — fine for demo, document the privacy story in the README.

---

## Deferred decisions

- **Database.** Likely SQLite if we need persistence for batch tracking; Postgres if we want a more production-shaped story. Punted until we know whether batch is in scope.
- **Agent input form shape.** Field-by-field form vs. JSON paste vs. CSV-style row. Shapes both UX and API contract.
- **Batch upload UX.** Zip of images + CSV of expected values? Multiple image uploads + one CSV? Per-row API calls? Affects the batch endpoint shape directly.
- **OpenAI output mode.** Structured outputs (JSON schema enforced) vs. JSON mode vs. free-form + parse. Leaning structured outputs — they're the most robust to drift.
- **Vision call topology.** One call extracts everything, *or* two calls (one for fields, one specifically for the warning statement). Splitting may be cleaner since the warning needs different evidence (bold detection, exact text), but doubles latency.

---

## Stack summary

| Layer | Choice |
|---|---|
| Frontend | React + Vite |
| Backend | FastAPI (Python) |
| Vision | OpenAI vision via OpenRouter → direct OpenAI for demo |
| Comparison | Programmatic, per-field strictness |
| Storage (images) | Local disk (swap-ready) |
| Database | Deferred (likely SQLite) |
| Container | Multi-stage Dockerfile |
| Host | Railway (Azure Container Apps portable) |

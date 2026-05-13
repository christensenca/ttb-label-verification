# Feature Specification: Verify-and-Review Workflow

**Feature Branch**: `001-verify-and-review`

**Created**: 2026-05-13

**Status**: Draft

**Input**: User description: "End-to-end label verification workflow — preloaded queue (and user-added) of label image + expected-values pairs, single Start action moves items into processing, then a per-label review screen where a TTB-style reviewer compares extracted vs expected fields, sees confidence and pass/fail per field, can override failures with comments, and finally approves or rejects the item."

## Clarifications

### Session 2026-05-13

- Q: Should override work symmetrically (both Pass→Fail and Fail→Pass) or only Fail→Pass? → A: Symmetric — both directions supported. (Reaffirms FR-019 and Acceptance Scenario 4.4.)
- Q: When a reviewer chooses **Approve** while one or more fields are still in `Fail` state after overrides, should the system block the approval outright or require an explicit confirmation? → A: Require an explicit confirmation; do not block. (Reaffirms FR-023 and Acceptance Scenario 5.3.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Run the demo with one click (Priority: P1)

A reviewer opens the deployed prototype for the first time. The queue is already populated with fixture labels (image + expected-values pair per item), each in a `Loaded` state. The reviewer clicks **Start**, the system processes all loaded items in the background, and each item transitions through `Processing` to `Ready for Review`. The reviewer can immediately walk through the labels and approve or reject them without having to upload anything.

**Why this priority**: This is the smoke-test path for a "shared demo instance" — without it, an evaluator cannot see the product working. It is also the foundation for every other story (the queue, processing pipeline, and review surface are reused).

**Independent Test**: With no user-uploaded data, click Start, watch all preloaded items transition Loaded → Processing → Ready for Review, then open the first item and verify the review screen shows extracted values, expected values, per-field verdicts, and approve/reject controls.

**Acceptance Scenarios**:

1. **Given** a fresh visitor lands on the home screen, **When** the queue loads, **Then** at least one preloaded item is visible with status `Loaded`.
2. **Given** the queue contains only `Loaded` items, **When** the reviewer clicks **Start**, **Then** items transition to `Processing` and then to `Ready for Review`, with status visibly updating without a manual refresh.
3. **Given** at least one item is `Ready for Review`, **When** the reviewer opens it, **Then** the review screen renders the label image, expected values, extracted values, and per-field pass/fail verdicts.
4. **Given** the reviewer is on a `Ready for Review` item, **When** they click **Approve** or **Reject**, **Then** the item's status changes to `Approved` or `Rejected` and persists across page reload.

---

### User Story 2 — Add my own label + expected values to the queue (Priority: P1)

A reviewer wants to test a label they brought. They upload a label image plus a JSON document of expected values (brand, class/type, ABV, net contents, producer name and address, imported flag, country of origin). The item appears in the queue with status `Loaded`. Clicking **Start** processes all `Loaded` items — both preloaded and user-added — together.

**Why this priority**: Without this, the tool is a fixed demo. The interview's "Sarah workflow" depends on labels-in-hand being verifiable.

**Independent Test**: From the queue screen, add one new label + expected-values pair, see it appear with status `Loaded` next to the fixtures, click Start, and confirm the new item transitions to `Ready for Review` alongside the fixtures.

**Acceptance Scenarios**:

1. **Given** the reviewer is on the queue screen, **When** they choose **Add to queue** and provide both a label image and an expected-values JSON, **Then** a new queue item appears with status `Loaded`.
2. **Given** the reviewer attempts to add an item with a missing image OR missing/invalid expected-values JSON, **When** they submit, **Then** the system blocks the add and shows a specific reason (missing field, invalid JSON, etc.) without losing the partial input.
3. **Given** the queue contains a mix of preloaded and user-added `Loaded` items, **When** the reviewer clicks **Start**, **Then** both sets are processed together.

---

### User Story 3 — Review a label field-by-field with confidence and diffs (Priority: P1)

For each `Ready for Review` item, the reviewer sees fields grouped by semantic block (Identity, Producer, Quantitative, Origin, Government Warning), with each block presenting its fields in two columns — **Extracted** and **Expected (application JSON)** — plus the per-field verdict (Pass, Fail, or needs attention) and a confidence indicator. Where a field fails, the reviewer can see exactly which words differ between extracted and expected, highlighted inline.

**Why this priority**: The whole reason this tool beats eyeballing is the explainable diff. Without it, reviewers will not trust the verdict.

**Independent Test**: Open a `Ready for Review` item where at least one field passed and at least one field failed; verify the grouping, the two-column layout, the confidence indicators, and the inline diff highlighting on the failing field.

**Acceptance Scenarios**:

1. **Given** an item is open for review, **When** the screen renders, **Then** fields are visibly grouped into blocks (e.g., Identity: brand and class/type; Producer: producer name and address; Quantitative: ABV and net contents; Origin: is_imported and country_of_origin; Government Warning).
2. **Given** any field block, **When** the reviewer reads a row, **Then** they see Extracted, Expected, the verdict, the matching rule that produced the verdict (e.g., "fuzzy match", "numeric tolerance ±0.1%"), and a confidence indicator.
3. **Given** a failed text field (e.g., the Government Warning or producer name), **When** the row renders, **Then** the differing words/characters between Extracted and Expected are visually highlighted in both columns.
4. **Given** the confidence indicator on any field is low, **When** the field renders, **Then** it shows a subtle visual cue (not a blocking alert) so the reviewer can prioritize their attention.

---

### User Story 4 — Open the source image and override a failed extraction (Priority: P2)

When a field fails — especially because extraction missed or misread it — the reviewer wants to consult the original image. They click the field (or a dedicated "view on image" affordance), the label image opens at a viewable size, and the reviewer can see for themselves what the label says. If the model was wrong and the field actually matches, the reviewer can **Override to Pass** with a note explaining why. The override is recorded as a human decision separate from the model's verdict; both persist for audit.

**Why this priority**: Image-quality robustness was flagged as out of scope for v1; manual override is what makes that deferral acceptable. Without override, a single bad extraction blocks an otherwise-correct label.

**Independent Test**: Open an item with at least one failed field, click the field to open the image, then override it to Pass with a comment. Confirm the field row now shows the override state, the comment is captured, and reopening the item later shows the override persisted.

**Acceptance Scenarios**:

1. **Given** any field row, **When** the reviewer clicks to open the source image, **Then** the label image opens at a size large enough to read the relevant region without leaving the review screen.
2. **Given** a field with verdict `Fail`, **When** the reviewer chooses **Override to Pass**, **Then** they are prompted for a short comment, the field is marked as overridden, and the override is attributed to a human decision (not the model).
3. **Given** a field has been overridden, **When** the reviewer or anyone else later opens the item, **Then** the override, the comment, and the original model verdict are all still visible.
4. **Given** a field was passed by the model, **When** the reviewer wants to flip it to Fail, **Then** the same override mechanism is available in reverse (override-to-fail) and behaves symmetrically.

---

### User Story 5 — Approve or reject the item with notes (Priority: P1)

At the bottom of the review screen, after reviewing each field block, the reviewer makes a final call on the whole item: **Approve** or **Reject**. They can type a free-text comment that applies to the item as a whole. If they choose **Reject**, they tick a checklist of which specific field-level failures drove the rejection — so the rejection reason is structured, not just narrative.

**Why this priority**: A submission is not "verified" until a human says so. The structured reject-reason is what makes the audit trail useful downstream.

**Independent Test**: On a `Ready for Review` item, leave a comment, tick one or more failure reasons, click **Reject**; reload the item and confirm the final status, comment, and the specific reasons selected all persisted.

**Acceptance Scenarios**:

1. **Given** an open review item, **When** the reviewer scrolls to the decision area, **Then** they see **Approve** and **Reject** controls and a free-text comment field.
2. **Given** the reviewer chooses **Reject**, **When** the rejection panel opens, **Then** it lists every field currently verdicted as `Fail` (after overrides) as a checkbox the reviewer can tick to flag as the rejection reason; at least one must be selected to submit a rejection.
3. **Given** the reviewer chooses **Approve**, **When** any field still has verdict `Fail` after overrides, **Then** the system asks for explicit confirmation before approving ("There are still N failing fields — approve anyway?").
4. **Given** the reviewer submits the decision, **When** the item reloads or they navigate back, **Then** the final status (`Approved` or `Rejected`), the comment, and the selected rejection reasons (if any) are all visible.

---

### User Story 6 — Reset the shared demo (Priority: P3)

Because the deployed instance is shared, any visitor can leave the queue in a half-reviewed state. A reset action wipes user-added items and review decisions, restoring the queue to the original preloaded fixtures in `Loaded` state.

**Why this priority**: Operational hygiene for a shared demo. Not user-facing value, but without it the second visitor sees the first visitor's mess.

**Independent Test**: After approving/rejecting at least one preloaded item and adding at least one user item, trigger reset; confirm the queue matches the original fixture set in `Loaded` state and the user-added items are gone.

**Acceptance Scenarios**:

1. **Given** the queue has been modified (items reviewed or added), **When** the reviewer triggers **Reset demo**, **Then** they are asked to confirm because the action is destructive.
2. **Given** the reviewer confirms reset, **When** the action completes, **Then** the queue contains only the original fixture items, each in `Loaded` state, and no review decisions remain.
3. **Given** the deployed instance is shared, **When** any visitor opens the page, **Then** a persistent banner makes clear that data is visible to everyone with the link.

---

### Edge Cases

- **Extraction failed (model error, timeout, unreadable image).** The item lands in the review queue with status `Extraction Failed`. The reviewer sees the image, the expected values, and a clear "we couldn't extract this label" message; they can still **Override to Pass** field-by-field or reject the item with a reason. No silent dropping.
- **JSON missing optional fields** (e.g., domestic label with no `country_of_origin`). The corresponding row still renders, marked "not applicable" rather than failing.
- **`is_imported: true` but `country_of_origin` missing** on the expected side. The expected-values upload is rejected up front with a specific error.
- **Multiple labels uploaded as a batch.** All `Loaded` items begin processing together when Start is clicked; the queue shows progress for each. Failures in one item never block the others.
- **Reviewer navigates away mid-review.** Partial overrides and comments persist; on return, the item is still `Ready for Review` and the partial state is restored.
- **Reviewer attempts to approve with zero overrides and any field failing.** Allowed but requires explicit confirmation (Acceptance Scenario 5.3).
- **Very large batch (200–300 items).** The queue and processing must remain responsive; the reviewer should not have to wait for the whole batch to finish before reviewing items that are already `Ready for Review`.
- **Confidence is "low" but field matches.** The match still passes; the low-confidence cue is informational, not a verdict.
- **Government Warning fails on a single missing word.** The diff makes the specific missing word visible in both columns so the reviewer can verify at a glance.

## Requirements *(mandatory)*

### Functional Requirements

**Queue and intake**

- **FR-001**: The system MUST present a queue view listing every label item with its current status: `Loaded`, `Processing`, `Ready for Review`, `Approved`, `Rejected`, or `Extraction Failed`.
- **FR-002**: The system MUST ship with a preloaded set of fixture items (each: one image + one expected-values record) so a new visitor sees a non-empty queue without uploading anything.
- **FR-003**: Reviewers MUST be able to add a new item by providing both a label image and an expected-values document containing brand, class/type, ABV, net contents, producer name, producer address, `is_imported`, and (when imported) country of origin.
- **FR-004**: The system MUST validate the expected-values document on add and reject submissions with missing required fields or invalid structure, surfacing a specific reason.
- **FR-005**: The system MUST treat the Government Warning as always required for alcohol and MUST NOT require it to be supplied in the expected-values document (it is validated against a canonical reference text).

**Processing**

- **FR-006**: The system MUST provide a single **Start** action that moves every `Loaded` item into `Processing`.
- **FR-007**: When an item finishes processing successfully, it MUST transition to `Ready for Review` and a per-field result set (extracted value, verdict, matching rule, confidence) MUST be available for the review screen.
- **FR-008**: When an item fails to process, it MUST transition to `Extraction Failed` rather than disappearing; the reviewer MUST be able to open it and review what is available.
- **FR-009**: The processing pipeline MUST NOT auto-approve any item; every item requires an explicit human decision.
- **FR-010**: The reviewer MUST be able to open and review any item that is `Ready for Review` while other items in the same batch are still `Processing`.

**Review screen — structure**

- **FR-011**: For each item being reviewed, the system MUST display the label image alongside the field results.
- **FR-012**: Field results MUST be grouped into semantic blocks: **Identity** (brand, class/type), **Producer** (producer name, producer address), **Quantitative** (ABV, net contents), **Origin** (`is_imported`, country of origin), and **Government Warning**.
- **FR-013**: Within each group, each field MUST be presented in a two-column layout: **Extracted** value on one side, **Expected** value on the other.
- **FR-014**: Each field MUST display its verdict (`Pass`, `Fail`, `Overridden`, or `Not Applicable`), the matching rule used to produce the verdict (e.g., "fuzzy match", "numeric tolerance ±0.1%", "exact match"), and a confidence indicator.
- **FR-015**: The confidence indicator MUST be a subtle visual cue when confidence is low — specifically: not flashing, not animated, smaller than the verdict pill, in a non-alert color. Passing fields with low confidence still pass; the indicator never blocks an action.

**Review screen — diff and image**

- **FR-016**: For text fields with verdict `Fail`, the system MUST visually highlight the differing words/characters between the Extracted and Expected values in both columns so the reviewer can see at a glance what differs.
- **FR-017**: For the Government Warning specifically, the diff MUST be word-aware so reviewers can identify a missing or altered word in the canonical text.
- **FR-018**: From any field row, the reviewer MUST be able to open the source label image without leaving the review screen. The opened view MUST occupy at least 60% of the viewport's shorter dimension and MUST support either zoom-on-scroll or click-to-zoom so a reviewer can inspect a specific region.

**Review screen — override and decision**

- **FR-019**: From any field row, the reviewer MUST be able to override the verdict (Pass→Fail or Fail→Pass) and MUST be prompted to enter a short comment when doing so.
- **FR-020**: Overridden verdicts MUST display visually distinct from model-produced verdicts, and the original model verdict MUST remain visible for audit.
- **FR-021**: At the bottom of the review screen, the system MUST present **Approve** and **Reject** controls and an item-level free-text comment field.
- **FR-022**: Choosing **Reject** MUST open a panel listing every field currently in `Fail` state (after overrides) as checkboxes; the reviewer MUST select at least one checkbox to submit the rejection. The selected items become the structured rejection reasons.
- **FR-023**: Choosing **Approve** while one or more fields remain in `Fail` state (after overrides) MUST require an explicit confirmation step.
- **FR-024**: Once the reviewer submits a final decision, the item's status MUST become `Approved` or `Rejected` and MUST persist across reload, including the comment, the rejection reasons (if any), and every per-field decision and override.

**Demo operation**

- **FR-025**: The system MUST display a persistent banner on the deployed instance making clear that the data is visible to all visitors and that the instance is a shared demo.
- **FR-026**: The system MUST provide a **Reset demo** action that wipes user-added items and all review decisions and restores the queue to the original fixture set in `Loaded` state.
- **FR-027**: The reset action MUST require an explicit confirmation before executing.

### Key Entities *(include if feature involves data)*

- **Submission**: One label sitting in the queue. Has a status (`Loaded` / `Processing` / `Ready for Review` / `Approved` / `Rejected` / `Extraction Failed`), a source image, an expected-values record, a timestamp, and an indicator of whether it is a fixture or user-added.
- **Expected Values**: The application-side data the label is being verified against — brand, class/type, ABV, net contents, producer name, producer address, `is_imported`, country of origin (required iff imported). Government Warning is validated separately against the canonical reference text and is not part of expected values.
- **Extraction Result**: Per submission, the per-field extracted value plus the model's confidence and any structural flags relevant to the field (e.g., for the Government Warning, whether it was rendered in bold and all-caps).
- **Comparison Result**: Per submission and per field, the verdict (`Pass` / `Fail` / `Not Applicable`), the matching rule applied, and the evidence (the specific differing tokens for text fields).
- **Review Decision**: The human decisions on a submission — per-field overrides (each with a comment), the item-level decision (`Approved` / `Rejected`), the item-level comment, and (for rejections) the structured set of failing fields chosen as the rejection reason.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time visitor can move from page-load to viewing per-field verdicts on a preloaded item with no more than two interactions (click **Start**, click an item).
- **SC-002**: A reviewer can assess and decide a label in under 60 seconds on a typical item (no extraction failures, fewer than two overrides), measured from opening the item to submitting Approve/Reject.
- **SC-003**: For any failed text field, a reviewer can identify what differs between the extracted and expected values in under 5 seconds of reading the row — without opening the image — at least 90% of the time during informal usability checks.
- **SC-004**: When a model extraction is wrong but the label is actually compliant, a reviewer can override the field and approve the item in under 30 seconds.
- **SC-005**: After **Reset demo**, the queue returns to its original fixture state with 100% reliability — no user-added items remain and no review decisions persist.
- **SC-006**: When a batch of items is processing, items that have finished are reviewable within 3 seconds of completion (the queue-polling interval ceiling), without waiting for the rest of the batch.
- **SC-007**: The final approve/reject decision, the comment, every per-field override, and the structured rejection reasons all survive page reload — verified by reloading after every submitted decision during validation.

## Assumptions

- **Single-user prototype, no authentication.** Anyone with the link can review any item. This matches the "shared demo instance" framing in the architecture decisions.
- **No PII concerns for the exercise.** Label and expected-values data is treated as non-sensitive.
- **Reviewer is a domain-aware human** (TTB-style label reviewer or a stand-in evaluator). The UI is designed for that persona — not for unauthenticated public consumers and not for full novices.
- **Fixtures are good enough to demonstrate variety.** The preloaded set covers at least one passing item, one item with a textual diff in the Government Warning, one item with a producer-address normalization case, and one numeric-tolerance case on ABV.
- **A reviewer reviews one item at a time.** Bulk approve/reject across items is not part of this feature.
- **The same reviewer who triggers Start may also review.** There is no separate operator vs. reviewer role.
- **The Government Warning canonical text is treated as a known fixed reference.** Its content is fixed for the purposes of this feature; updates to the canonical text are out of scope.
- **Image quality is "reasonable."** Robustness to extreme angles, glare, or low resolution is explicitly deferred. The Override workflow exists in part to compensate.
- **Processing is fast enough to feel interactive.** Per the architecture latency budget, each item processes in seconds, not minutes. The queue UI assumes that scale.

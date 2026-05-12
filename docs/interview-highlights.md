# Interview Highlights

Synthesis of the four stakeholder interviews in [assigment.md](../assigment.md), organized into a product picture and a list of unresolved tensions.

## The problem in one paragraph

TTB reviews ~150,000 label applications/year with 47 agents. Most of the work is rote matching — brand name, ABV, warning text — between a submitted application and the label artwork. Agents are drowning in routine checks; leadership wants AI to take the routine cases off their plate so humans can focus on the judgment cases. This prototype is a standalone proof-of-concept, not a COLA integration.

## What the product needs to do

**Core verification (must-have)**
- Extract the standard required fields from a label image: brand name, class/type, ABV, net contents, producer/bottler name & address, country of origin (imports), Government Health Warning.
- Compare extracted values against expected values (whatever the agent is reviewing against — see open question below) and flag matches/mismatches.
- Special-case the Government Warning: must be exact wording, `GOVERNMENT WARNING:` in all caps and bold. This is the most-gamed field — vendors shrink it, retitle it, bury it.
- Apply field-appropriate matching strictness — not everything is exact-match (see Dave's `STONE'S THROW` vs `Stone's Throw` example).

**Performance (hard constraint)**
- ≤5 seconds per label end-to-end. The previous scanning vendor pilot died at 30–40s because agents could eyeball five labels in that time. Miss this and the tool gets shelved.

**UX (hard constraint)**
- Designed for the 73-year-old benchmark. Clean, obvious, no hunting for buttons. Half the team is over 50; tech literacy spans Dave (prints emails) to Jenny (could've built this herself).
- Show the agent *why* something passed or failed — so they can sanity-check the AI in <2 seconds and move on. Don't make the human do more work than the manual process.

**Batch (high-value want)**
- Importers dump 200–300 labels at a time; currently processed one-by-one. Bulk upload + queue view would be a big win even if review is still per-label.

## Constraints & non-goals

- **Standalone prototype.** No COLA integration. No PII storage. No FedRAMP-level concerns for this exercise — Marcus said "just don't do anything crazy."
- **Eventual production deployment runs on a locked-down federal network** (Azure, blocks outbound to many domains, including ML endpoints during the last pilot). This doesn't constrain the *prototype's* hosting, but a hosted-API-only architecture flags a future portability problem worth calling out.
- **Image quality robustness is explicitly nice-to-have, not required.** Jenny flagged angles/lighting/glare as a real-world pain point but called it "maybe out of scope for a prototype."

## What this tells us to build

A web app where an agent uploads a label image (single or batch), the system OCRs/extracts fields, compares them to expected values, and returns a per-field pass/fail with the evidence (extracted text + confidence) in under 5 seconds. The Government Warning gets a stricter, dedicated check. Results UI is dense, scannable, and obvious — designed so an agent can confirm the AI's work in seconds, not minutes.

---

## Inconsistencies & open questions for reconciliation

1. **Strict vs. fuzzy matching.** Dave wants judgment (`STONE'S THROW` ≈ `Stone's Throw`); Jenny wants exact-match on the Government Warning (rejected a submission for title-case instead of all-caps). → *Resolution:* per-field strictness. Most fields use normalized/fuzzy comparison; the warning statement is exact-match including case and formatting. Worth surfacing the matching rule in the UI so agents trust it.

2. **What is the label being compared *against*?** Sarah describes the job as "what's on the label matches what's in the application" — implying a form + label pair. The technical requirements only describe a label image. → *Resolution needed:* does our prototype accept (a) just a label and extract fields, (b) a label + an expected-values form/JSON, or (c) both? Defaulting to (b) with a manual form is the most defensible MVP — it mirrors the real workflow.

3. **5-second SLA vs. batch of 300.** Sarah wants both. A 300-label batch at 5s/label serially is 25 minutes; parallel makes it tractable but raises cost/concurrency questions. → *Resolution needed:* is "5 seconds" per-label latency (agent waiting on one result) or end-to-end batch completion? Almost certainly the former — clarify in README.

4. **Cloud APIs vs. firewall reality.** Marcus says outbound calls to ML endpoints get blocked on the TTB network. The prototype is hosted externally so this doesn't bite today, but if the architecture is "OpenAI/Anthropic API → result" then real deployment requires either an allowlist or an on-prem model. → *Resolution:* fine for prototype, but document the dependency and the portability path.

5. **"Standalone prototype" vs. ambitious scope creep.** Marcus said keep it simple; Jenny floated bad-image handling; Sarah floated batch. → *Resolution:* core verification + clean UX first. Batch second if time. Image-quality robustness explicitly deferred.

6. **Dave's skepticism is a signal, not noise.** "Don't make my life harder" is the failure mode to avoid. The tool has to be net-faster than eyeballing, or veterans will route around it like they did with the last vendor.

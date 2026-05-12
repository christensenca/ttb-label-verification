# TTB Label Requirements — Engineering Reference

Source-grounded reference for the verification prototype. Pulled from 27 CFR (Cornell LII mirror). Citations inline. Federal regs change — re-verify before any production claim.

## Beverage classes covered

TTB regulates three classes, each with its own mandatory-info section in 27 CFR:

| Class | CFR section | Notes |
|---|---|---|
| Wine | [27 CFR 4.32](https://www.law.cornell.edu/cfr/text/27/4.32) | Brand label vs. any-label split matters |
| Distilled spirits | [27 CFR 5.63](https://www.law.cornell.edu/cfr/text/27/5.63) | Brand + class/type + ABV must share one field of vision |
| Malt beverages (beer) | [27 CFR 7.63](https://www.law.cornell.edu/cfr/text/27/7.63) | ABV only mandatory in specific cases |

The Government Warning ([27 CFR Part 16](https://www.law.cornell.edu/cfr/text/27/16.21)) applies to **all three**.

---

## Mandatory fields by class

### Wine — 27 CFR 4.32

**On the brand label:**
- Brand name (§ 4.33)
- Class, type, or other designation (§ 4.34)
- Exact % by volume of foreign wine in American/foreign blends (when foreign content is referenced)

**Anywhere on container:**
- Name and address of producer/bottler (§ 4.35)
- Net contents (§ 4.37) — non-standard fills must be on the front label
- Alcohol content (§ 4.36)

**Conditional disclosures:** FD&C Yellow No. 5, cochineal extract/carmine, sulfites ("Contains sulfites" if SO₂ ≥ 10 ppm).

### Distilled spirits — 27 CFR 5.63

**Must appear in the same field of vision (i.e., visible on one side without rotating the bottle):**
- Brand name (§ 5.64)
- Class/type designation (subpart I)
- Alcohol content (§ 5.65)

**Anywhere on container:**
- Name and address of bottler/distiller/importer (§§ 5.66–5.68)
- Net contents (may be blown/embossed/molded into the container)

**Conditional disclosures:** neutral spirits %, coloring/wood treatment, age statement, state of distillation (certain US whiskeys), FD&C Yellow No. 5, cochineal/carmine, sulfites, aspartame (`PHENYLKETONURICS: CONTAINS PHENYLALANINE`).

### Malt beverages — 27 CFR 7.63

- Brand name (§ 7.64)
- Class/type designation (subpart I)
- Alcohol content (§ 7.65) — **only mandatory** if the beer contains alcohol from added non-beverage flavors/ingredients (hops extract excluded)
- Name and address of bottler/importer (§§ 7.66–7.68) — may be molded into container
- Net contents (§ 7.70) — may be molded into container

**Conditional disclosures:** FD&C Yellow No. 5, cochineal/carmine, sulfites, aspartame.

---

## Field-format rules the verifier must enforce

### Alcohol content

| Class | Acceptable format | Tolerance |
|---|---|---|
| Wine (§ 4.36) | `Alcohol __% by volume` or range `Alcohol __% to __% by volume`; abbreviations `alc.`, `vol.` permitted | ±1% if >14% ABV; ±1.5% if ≤14% ABV. Range spread: ≤2% (>14%) or ≤3% (≤14%) |
| Spirits (§ 5.65) | `Alcohol __ percent by volume`, `__ percent alcohol by volume`, `Alcohol by volume __ percent`. Examples accepted: `40% alc/vol`, `Alc. 40% by vol.`, `Alc 40% by vol`, `40% Alcohol by Volume`. Proof may also appear (same or different field of vision) | ±0.3 percentage points |
| Beer (§ 7.65) | Same three formats as spirits. Round to nearest 0.1% (≥0.5% ABV) | ±0.3 percentage points |

Wine ≤14% ABV may omit the ABV statement entirely if labeled `table wine` or `light wine` (§ 4.36).

### Wine label legibility — § 4.38

- Mandatory info must appear on a **contrasting background**, readily legible.
- Type size: **≥2 mm** for containers >187 mL; **≥1 mm** for ≤187 mL.
- ABV statement: **between 1 mm and 3 mm** on containers ≤5 L, and **may not** be set off with a border or otherwise accentuated.
- Must be in English (limited exceptions for brand names and producer info).
- Labels must not be removable without water/solvents.

> Spirits (Part 5) and beer (Part 7) have analogous general-labeling sections; the prototype should treat wine's 2 mm / 1 mm thresholds as a reasonable proxy unless verifying a non-wine container against its own subpart.

### Brand name — distilled spirits (§ 5.64)

- A brand name is mandatory; if absent, the bottler/distiller/importer name acts as the brand.
- Brand names that create an "erroneous impression or inference as to the age, origin, identity, or other characteristics" are prohibited.
- A potentially misleading name may be cured by qualifying with `brand` or similar, subject to TTB officer approval.

---

## Government Health Warning — 27 CFR Part 16

### Exact required text (§ 16.21)

> **GOVERNMENT WARNING:** (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.

This applies to **all** alcoholic beverages ≥0.5% ABV bottled for sale or distribution in the US.

### Format/legibility rules (§ 16.22)

- `GOVERNMENT WARNING` — **all caps and bold**. The remainder of the statement **must not be bold**.
- Readily legible under ordinary conditions, on a **contrasting background**.
- Must be separated from other information on the label.
- Cannot be compressed such that legibility suffers.

**Minimum type size by container volume:**

| Container | Min type size | Max chars/inch |
|---|---|---|
| ≤237 mL (≤8 fl oz) | 1 mm | 40 |
| >237 mL to 3 L | 2 mm | 25 |
| >3 L | 3 mm | 12 |

---

## Product notes — implications for the verifier

These are decisions/uncertainties the agents and product team should weigh in on before we lock the spec.

1. **Exact-match vs. semantic-match for brand name.** Per Dave's `STONE'S THROW` vs. `Stone's Throw` story, the regs target *misleading* names, not capitalization. Recommendation: normalize case/whitespace/punctuation for brand-name comparison; flag for human review rather than auto-reject when normalized strings match.
2. **The Government Warning *is* exact-match territory.** Jenny's `Government Warning` (title case) rejection is correct — § 16.22 requires the lead-in in all caps + bold. The verifier should check (a) verbatim text presence, (b) `GOVERNMENT WARNING:` in all caps, (c) the remainder *not* bolded, (d) contrasting background, (e) minimum type size for the declared container volume. (d) and (e) are the hardest to verify from a photo and likely need agent confirmation.
3. **ABV format is a regex-able problem, not just a number match.** Spirits accept four equivalent phrasings; wine accepts a range syntax; beer rounds to 0.1. The verifier must parse the *format* and the *value* separately, and apply the right tolerance per class (±0.3 spirits/beer, ±1.0/±1.5 wine).
4. **Field-of-vision constraint (spirits only).** § 5.63 requires brand + class/type + ABV to be visible together on one side. With a single front-label photo this is naturally testable; with multi-image batch uploads (Janet's Seattle use case) we need to know which images are "front" vs. "back/side."
5. **Net contents and producer address can be molded into glass** (beer and spirits). OCR against a flat label image will miss these; the verifier should either request a separate image or surface a "cannot verify from this image" status rather than rejecting.
6. **Conditional disclosures depend on knowing the ingredients** (sulfites, FD&C Yellow #5, aspartame, cochineal). The app cannot verify presence/absence from a label image alone — these must come from the application form, and we verify *consistency* (form says contains sulfites → label must say so).
7. **Wine ≤14% ABV with "table wine" / "light wine" designation can omit ABV entirely.** Don't flag a missing ABV on these as an error.
8. **Class/type designations are a closed vocabulary** defined in each subpart's class/type section (e.g., "Kentucky Straight Bourbon Whiskey," "Imperial IPA"). The verifier should validate the *string is on the label* and matches the application — it should not try to verify whether the product *actually qualifies* for the class (e.g., real bourbon-age compliance). That's the agent's judgment call.
9. **5-second performance ceiling** (Sarah's scanning-vendor lesson) constrains how many round-trips we can make to a vision model. Favor one structured extraction call that returns all fields at once, then run cheap deterministic checks (regex, tolerance math, exact-string match) locally.

---

## Sources

- [27 CFR 4.32 — Mandatory label information (wine)](https://www.law.cornell.edu/cfr/text/27/4.32)
- [27 CFR 4.36 — Alcoholic content (wine)](https://www.law.cornell.edu/cfr/text/27/4.36)
- [27 CFR 4.38 — General wine label requirements](https://www.law.cornell.edu/cfr/text/27/4.38)
- [27 CFR 5.63 — Mandatory label information (distilled spirits)](https://www.law.cornell.edu/cfr/text/27/5.63)
- [27 CFR 5.64 — Brand names (distilled spirits)](https://www.law.cornell.edu/cfr/text/27/5.64)
- [27 CFR 5.65 — Alcohol content (distilled spirits)](https://www.law.cornell.edu/cfr/text/27/5.65)
- [27 CFR 7.63 — Mandatory label information (malt beverages)](https://www.law.cornell.edu/cfr/text/27/7.63)
- [27 CFR 7.65 — Alcohol content (malt beverages)](https://www.law.cornell.edu/cfr/text/27/7.65)
- [27 CFR 16.21 — Health Warning Statement (text)](https://www.law.cornell.edu/cfr/text/27/16.21)
- [27 CFR 16.22 — Health Warning Statement (legibility)](https://www.law.cornell.edu/cfr/text/27/16.22)

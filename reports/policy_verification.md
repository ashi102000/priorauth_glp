# Policy Verification Packet (Phase 2, blocking)

All three policies are normalized from **primary payer documents** retrieved on 2026-09-29. Verbatim excerpts are saved under `policies/sources/`.

`scripts/check_policies.py` validates each policy file against `schemas/policy.schema.json`. It also confirms that every quoted segment (24 of them) appears **verbatim** in the saved source text, after whitespace normalization.

Status: **UNVERIFIED — waiting for user sign-off.**

## Documents

| Policy ID | Document | Version / date as printed | In force on index date 2026-09-01? |
|---|---|---|---|
| `BCBS_FEP_WEGOVY_2026_07_01` | FEP Medical Policy 5.99.030 "Saxenda Wegovy" | Effective July 1, 2026; last review June 11, 2026 | Yes. The Feb 13, 2026 version has word-for-word identical adult criteria. |
| `AETNA_WEGOVY_4774C_2026_08_20` | Aetna Specialty Pharmacy CPB "Wegovy PA with Limit 4774-C P08-2025 v5" | Unlabeled page date "August 20, 2026"; no effective-date field | Presumed yes. |
| `UHC_WEGOVY_P1114_22_2026_09_01` | UHC "Prior Authorization/Notification – Plans with Weight Loss/Appetite Suppression Medication Coverage" | Program 2026 P 1114-22; Effective 9/1/2026 | Yes. It takes effect exactly on the index date. |

## Criteria side by side (adult, initial authorization, chronic weight management)

| Requirement | BCBS FEP | Aetna 4774-C | UHC P1114-22 |
|---|---|---|---|
| Age | ≥ 18 (adult branch) | ≥ 18 | ≥ 12 (all adults pass) |
| BMI | ≥ 30, or ≥ 27 + (established CVD **or** weight-related comorbidity) | *Baseline* ≥ 30, or ≥ 27 + weight-related comorbidity (documented) | ≥ 30, or ≥ 27 + weight-related comorbidity |
| Comorbidity examples ("e.g.", not exhaustive) | T2DM, dyslipidemia, HTN; CVD list | HTN, T2DM, dyslipidemia | dyslipidemia, HTN, T2DM, sleep apnea |
| Lifestyle | **Has participated** in a comprehensive weight-management program. No duration. | **≥ 6 months** of a comprehensive program (behavioral + reduced-calorie diet + physical activity, with continuing follow-up) **before** drug therapy; **plus** the drug will be used with diet **and** activity | Drug will be used **as an adjunct** to lifestyle modification (any of diet, exercise, behavioral, or community program). No duration. |
| Concurrent GLP-1 / weight-loss drug | **No** dual GLP-1 therapy; **no** dual PA weight-loss drug therapy | Not a criterion (FDA-label note only) | Not a criterion (removed 2013) |
| Prior failed attempts / inadequate response | Not required | Not required | Not required |
| BMI recency window | None | None | None |
| Initial approval duration | 6 months | 8 months | 5 months |

**Consequence for the benchmark:** none of the three policies requires *inadequate response*. The cohort's response-related challenges (GLP1-025 missing response, GLP1-035 limited improvement) therefore don't change any payer's PA outcome. They remain as distractor reasoning load, and `inadequate_response` is not a scored criterion.

## Evaluator assignment (policy-as-code)

- **Code:** `age`, `indication`, and `bmi_threshold`. The BMI arithmetic and threshold are code; the comorbidity *presence* check feeds in from structured Conditions and semantic evidence.
- **Semantic (Jev or GPT, depending on the pipeline):**
  - FEP `weight_management_program`
  - Aetna `program_6_months` (models extract dated START/CONTINUATION/STOP events; **code** computes calendar whole months)
  - Aetna `adjunct_diet_and_activity`
  - UHC `lifestyle_adjunct`
  - FEP `no_concurrent_glp1` and `no_concurrent_pa_weight_loss_med`

## Criterion status vocabulary and PA aggregation (proposed)

Each criterion resolves to one of four statuses:
- `PASS`: clearly met.
- `FAIL`: clearly not met, e.g. BMI below threshold, or the program was declined or stopped.
- `INSUFFICIENT`: the required evidence is not documented. Missing is **not** treated as negative, but the case cannot be auto-submitted.
- `CONFLICT`: the evidence is genuinely contradictory, or ambiguous in a way that can't safely be resolved automatically.

PA state is derived from the criterion statuses:
- `NOT_READY` if any criterion is `FAIL` or `INSUFFICIENT`.
- Otherwise `REVIEW_REQUIRED` if any criterion is `CONFLICT`.
- Otherwise `READY`.

The binary auto-submission flag is `READY → true`; everything else → `false`.

## Interpretation choices needing sign-off

1. **FEP version ID.** Use the version in force on the index date (`…_2026_07_01`) rather than `…_2026_02_13`. The criteria are identical either way.
2. **Aetna version.** Model the standard 4774-C, and use its unlabeled date "August 20, 2026". Do not model the variants 6450-C (BMI ≥ 35) or 7046-C (state-specific).
3. **Aetna 6-month duration** is `whole_calendar_months(first program evidence → last documented participation) ≥ 6` over a **continuous** period.
   - A stop or lapse breaks continuity.
   - Vague durations ("several months", "for years") can't establish ≥ 6 months, so the criterion is `INSUFFICIENT`, or `CONFLICT` if there's contradicting evidence.
   - Diet-only, exercise-only, and counseling-only efforts are not a *comprehensive* program.
4. **"Adjunct" criteria** (UHC `lifestyle_adjunct`, Aetna `adjunct_diet_and_activity`) are judged from documentation around the request.
   - An explicit "not following any diet/exercise plan" is `FAIL`.
   - No lifestyle documentation at all is `INSUFFICIENT`.
   - For UHC, any single ongoing modality (diet *or* exercise) passes.
5. **Conflicting medication evidence** (FEP only):
   - When a **newer, explicit** clinical statement contradicts an **older** structured record, the newer statement governs, so the criterion is `PASS`. Examples: GLP1-038, a stopped Ozempic still listed as an active order; GLP1-039, a stale 2023 Wegovy statement omitted from the current med review.
   - When **structured evidence is newer** than the narrative, it's `CONFLICT`. Example: GLP1-045, where a Zepbound pharmacy fill comes *after* the "stopped" call.
   - Unknown current status is `INSUFFICIENT`. Examples: GLP1-024 and GLP1-050.
6. **Structured vs narrative BMI.** The latest **recorded structured BMI** governs, per the cohort-wide rule (GLP1-040: 29.7, not the outside form's 30.4).
7. **Comorbidity** (only needed when 27 ≤ BMI < 30):
   - An active structured Condition or clear narrative documentation counts. GLP1-022 and GLP1-034 are narrative-only.
   - A resolved condition does not count (GLP1-046).
   - Elevated BP without a diagnosis does not establish hypertension. GLP1-028 is therefore `CONFLICT`/`INSUFFICIENT`, pending decision.

## Not modeled (documented in each JSON's `out_of_scope`)

- FEP Blue Focus (non-formulary)
- The UHC North Dakota EHB variant (BMI ≥ 40)
- Plans without weight-loss coverage
- The Aetna variant policies
- Pediatric, MASH, CV, and tablet sections
- Quantity limits and approval durations

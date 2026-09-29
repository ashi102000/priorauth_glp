# TODO / Open items

## Phase 1 — Dataset
- [x] M1.1 Scaffold + cohort validation (validate_cohort.py PASS)
- [x] M1.2 Seeded timelines + note plans + draft evidence map (awaiting user review)
- [x] M1.3 Notes written — all 50 patients (data/notes/src → data/notes/*.json)
- [x] M1.4 Note lint / consistency — `lint_notes.py --strict` PASS (50/50); incidental comorbidity scan → evidence_map
- [x] M1.5 FHIR R4 transaction bundles — 50 bundles / 2,358 resources; strict R4 + R4B validation PASS
- [x] M1.6 Local FHIR source (replaces HAPI per user) — LocalBundleClient + verify_local_fhir.py PASS
- [x] M1.7 Cohort QA report (reports/cohort_qa.md) + pytest suite (83 passed) — Phase 1 complete, reviewed by user 2026-09-29

## Phase 2 — Policies
- [x] P2.1 Research the three payer policies — primary sources saved under policies/sources/
- [x] P2.2 Normalized policies/*.json (3) — schema + 24 verbatim quote segments PASS (scripts/check_policies.py)
- [x] P2.3 USER VERIFICATION — approved 2026-09-29 (reports/policy_verification.md)
- [x] P2.4 Policy loader + deterministic evaluator (code criteria + PA aggregation), 14 tests
- [x] P2.5 criterion_truth.json (750 labels) + pa_truth.json (150) — awaiting user review of reports/ground_truth_summary.md

## Phase 3 — Evidence pipeline
- [x] Feature extraction, chunking, BM25 criterion retrieval (+ earliest/latest for temporal), evidence profiles (cached, guarded)
- [x] Retrieval evaluation vs evidence map — reports/retrieval_eval.md, results/retrieval/retrieval_results.csv

## Phase 4 — GPT baseline (next)
- [x] OpenAI provider (Responses API, strict JSON schema), trace logging, verified pricing (config/model_pricing.json)
- [x] GPT pipeline; smoke test 5 patients x 3 policies: 15/15 PA, 75/75 criteria, $0.23

## Phase 5 — Jev (next)
- [x] Read live TypeSafe docs; JevProvider (raw HTTP, noul/choice/score, exact raw probabilities, retries, guard)
- [x] Pinned jev-1.13.0 @ https://api.typesafe.ai; pricing $0.042/Mtok input (verified); smoke test PASS

## Phase 6 — Hybrid (next)
- [x] Question sets, code composition, sensitivity-based confidence router, GPT escalation, READY-only narrative
- [x] Smoke test 15/15 (same patients as GPT smoke); 149 tests passing

## Phase 7 — Benchmark (next)
- [x] CLI runner with manifest-first, checkpoint/resume, request-keyed call cache, traces (153 tests)
- [x] main_gpt (150/150), main_hybrid_t0.90 (150/150), sweep 0.60–0.95 (5x150) — total new spend $4.25

## Phase 8 — Evaluation (next)
- [x] results/ outputs + presentation_results/ package + reports/evaluation_report.md + reports/failure_analysis.md (161 tests)
- [x] Results deck: presentation/sutter_jev_priorauth_results.html (41 slides; original left untouched). Recorded 6-slide demo walkthrough (GLP1-045 FEP) replaces live-app demo; added models/pricing, by-payer/difficulty, every-PA-error slides

## Phase 9 — Vercel UI (next)
- [x] Next.js app (web/): Overview, Patients, PA Workbench (replay + live for 10 curated cases via api/run_pa.py, server-side ground-truth reveal), Benchmark replay, Results — all from exported run data
- [x] Visual QA: desktop 1440, mobile 500, light + dark
- [ ] PARKED by user (2026-09-29): deploy to Vercel (user: `npx vercel login`; set OPENAI_API_KEY, OPENAI_MODEL, JEV_API_KEY, optional DEMO_PASSCODE / JEV_MODEL / JEV_AUTO_THRESHOLD; root directory web/)
- [x] Narrative: READY-only (configurable), reported decision-only vs end-to-end; escalation: uncertain criteria only

## Open questions
- [x] GLP1-041 BMI series resolved (see DECISIONS.md)
- [x] GLP1-029 records 30.0 (see DECISIONS.md)
- GLP1-030: spec 29.95 vs computed 29.94. Record the spec value 29.95 (<30 either way).
- GLP1-040/041: BMI-conflict scenarios are stored in the `medication_scenario` field; treated as data-conflict scenarios.
- Phase 2: GLP1-025 (`complete_response_missing`) — the narrative never characterizes response, but structured weights show a ~2% change. Decide whether a structured weight trend counts as "documented inadequate response."
- Phase 2: GLP1-039 — prior Wegovy use (2023, stale list). Check whether policies treat prior Wegovy use as a continuation request rather than an initial one.

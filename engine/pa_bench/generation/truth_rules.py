"""Ground-truth labeling rules (hidden; evaluation-only). Applies the user-approved interpretations
(DECISIONS.md 2026-09-29) to each cohort documentation_state / medication_scenario.

Keys per documentation_state:
  fep_program    FEP 'has participated in a comprehensive weight management program' (literal; no duration)
  aetna_program  Aetna '>= 6 months comprehensive program (diet + activity + behavioral, continuing follow-up)',
                 continuous calendar whole months; "COMPUTE" = derive from dated program events in the plan
  current_any    UHC 'adjunct to lifestyle modification' — any ongoing modality, documented near the request
  current_both   Aetna 'will be used with a reduced-calorie diet AND increased physical activity' — both, documented
Each entry carries a rationale string that is copied into criterion_truth.json.
"""
P, F, I, C = "PASS", "FAIL", "INSUFFICIENT", "CONFLICT"
COMPUTE = "COMPUTE"

_COMPLETE = {"fep_program": (P, "Enrolled in a comprehensive program with dietitian visits and follow-ups."),
             "aetna_program": (COMPUTE, "Continuous program with diet, activity and follow-up; duration computed from dated events."),
             "current_any": (P, "Final note documents continued diet and exercise."),
             "current_both": (P, "Final note documents continued diet AND exercise.")}

DOC_TRUTH: dict[str, dict[str, tuple[str, str]]] = {
    **{s: _COMPLETE for s in ("complete_6_5_months", "complete_7_months", "complete_8_months", "complete_9_months",
                              "complete_10_months", "complete_11_months", "complete_12_months", "complete_14_months",
                              "complete_response_missing", "complete_limited_improvement")},
    "absent": {
        "fep_program": (I, "No weight-management program documented anywhere."),
        "aetna_program": (I, "No weight-management program documented anywhere."),
        "current_any": (I, "No lifestyle modification documented near the request."),
        "current_both": (I, "No lifestyle modification documented near the request.")},
    "counseling_only": {
        "fep_program": (I, "Only brief counseling with a handout; counseling is not a program."),
        "aetna_program": (I, "Only brief counseling; no program, no follow-up, no duration."),
        "current_any": (I, "No interval diet/exercise efforts documented near the request (counseling ~9 months earlier)."),
        "current_both": (I, "No interval diet/exercise efforts documented near the request.")},
    "diet_only": {
        "fep_program": (I, "Solo dietary changes only; no comprehensive program documented."),
        "aetna_program": (I, "Diet-only effort; no activity component, no comprehensive program."),
        "current_any": (P, "Ongoing dietary changes (food tracking) documented at the request."),
        "current_both": (I, "Physical activity never documented.")},
    "exercise_only": {
        "fep_program": (I, "Solo exercise routine only; no comprehensive program documented."),
        "aetna_program": (I, "Exercise-only effort; no dietary component, no comprehensive program."),
        "current_any": (P, "Ongoing regular exercise documented at the request."),
        "current_both": (I, "Reduced-calorie diet never documented.")},
    "program_no_duration": {
        "fep_program": (P, "Currently participating in a named lifestyle program."),
        "aetna_program": (I, "Participation documented but no start date or duration recoverable."),
        "current_any": (P, "Follows program meal plan and exercise sessions."),
        "current_both": (P, "Follows program meal plan and exercise sessions.")},
    "start_no_followup": {
        "fep_program": (P, "Enrolled in an employer weight-management program at the start visit (literal reading)."),
        "aetna_program": (I, "Only a start note; no continuing follow-up or later participation documented."),
        "current_any": (I, "No lifestyle efforts documented after the start visit ~8 months earlier."),
        "current_both": (I, "No lifestyle efforts documented after the start visit.")},
    "several_months": {
        "fep_program": (I, "Informal diet/walking efforts; no program documented."),
        "aetna_program": (I, "No program; duration only 'past several months' (undated)."),
        "current_any": (P, "Working on diet and exercise, documented at the request."),
        "current_both": (P, "Diet changes and walking documented at the request.")},
    "long_standing_vague": {
        "fep_program": (I, "Long-standing informal dieting; no program documented."),
        "aetna_program": (I, "No dated program; 'dieted on and off for years' cannot establish a continuous program."),
        "current_any": (P, "Ongoing diet efforts and daily dog walking documented at the request."),
        "current_both": (P, "Ongoing diet and exercise efforts documented at the request.")},
    "exact_6_months": dict(_COMPLETE),
    "jan_start_july_followup": {
        **_COMPLETE,
        "aetna_program": (COMPUTE, "Start 01/20 and continuation 07/28 (no interruption documented); duration computed.")},
    "fragmented_multi_note": {
        **_COMPLETE,
        "aetna_program": (COMPUTE, "Referral, dietitian plan, exercise update and RN follow-up across notes; duration computed."),
        "current_any": (P, "RN check-in 06/14 documents ongoing meal plan and exercise (~2 months before request)."),
        "current_both": (P, "RN check-in 06/14 documents ongoing meal plan and exercise.")},
    "intermittent_program": {
        "fep_program": (P, "Enrolled in a dietitian-led program in October."),
        "aetna_program": (C, "Oct start, lapse Nov/Dec–Mar, restart Mar: ~7 months total but only ~5 continuous; whether an interrupted program meets 'at least 6 months' is genuinely ambiguous."),
        "current_any": (P, "More consistent with meal plan and exercise since spring."),
        "current_both": (P, "Meal plan and exercise documented at the request.")},
    "jan_start_feb_stop": {
        "fep_program": (P, "Enrolled in the Healthy Weight program in January (participation, later abandoned; literal reading)."),
        "aetna_program": (F, "Stopped the meal plan and exercise ~6 weeks after starting; never resumed."),
        "current_any": (I, "Final note only says diet/exercise was tried 'earlier this year'; no current modification documented."),
        "current_both": (I, "No current diet/exercise documented.")},
    "jan_mar_restart_july": {
        "fep_program": (P, "Enrolled in employer program in January (literal reading)."),
        "aetna_program": (F, "Longest continuous period ~3 months (Jan–Mar); restarted July; total ~5 months."),
        "current_any": (P, "Back on diet and walking plan since July."),
        "current_both": (P, "Diet and walking documented at the request.")},
    "pcp_8mo_dietitian_3mo": {
        "fep_program": (P, "Dietitian-led program since May."),
        "aetna_program": (C, "PCP states 8 months of dedicated efforts; dietitian intake (May) states no prior structured plan — contradictory sources."),
        "current_any": (P, "Ongoing diet and swimming documented."),
        "current_both": (P, "Ongoing diet and exercise documented.")},
    "negated_structured_program": {
        "fep_program": (F, "Declined the structured program and dietitian referral; referral closed, never enrolled."),
        "aetna_program": (F, "Never enrolled; no formal diet or exercise regimen."),
        "current_any": (F, "Final note: still no structured diet or exercise program."),
        "current_both": (F, "Final note: still no structured diet or exercise program.")},
    "clear_then_stopped_6_weeks": {
        "fep_program": (P, "Enrolled and participated ~6 weeks (literal reading: past participation counts)."),
        "aetna_program": (F, "Stopped ~6 weeks in after ankle injury; not resumed."),
        "current_any": (F, "Final note: not currently following a diet or exercise plan."),
        "current_both": (F, "Final note: not currently following a diet or exercise plan.")},
    "buried_across_many_notes": {
        **_COMPLETE,
        "aetna_program": (COMPUTE, "Program start (Dec) and continuation evidence scattered across notes; duration computed."),
        "current_any": (P, "Final note: 'despite staying with the program'."),
        "current_both": (P, "Program meal plan and exercise documented as ongoing.")},
    "one_relevant_many_distractors": {
        **_COMPLETE,
        "aetna_program": (COMPUTE, "Single note documents program since mid-December with monthly check-ins; duration computed."),
        "current_any": (P, "Final note documents ongoing plate method and walking."),
        "current_both": (P, "Final note documents ongoing diet and walking.")},
    "contradictory_program_dates": {
        "fep_program": (P, "Enrolled in a weight-management program (both sources agree on participation)."),
        "aetna_program": (C, "PCP: program since November 2025 (>= 6 months); dietitian: began April 2026 (< 6 months) — contradictory start dates."),
        "current_any": (P, "Continues the program."),
        "current_both": (P, "Meal plan and walking documented.")},
    "ambiguous_lifestyle": {
        "fep_program": (I, "Only vague lifestyle statements; no program documented."),
        "aetna_program": (I, "No program; no duration."),
        "current_any": (C, "'Trying to eat better', 'doing what he can', 'some walking' — too vague to confirm or rule out lifestyle modification."),
        "current_both": (C, "Too vague to confirm a reduced-calorie diet and increased activity.")},
}

# FEP medication-reconciliation criteria, keyed by medication_scenario: (glp1, pa_weight_loss_med)
MED_TRUTH: dict[str, dict[str, tuple[str, str]]] = {
    "none": {"glp1": (P, "No GLP-1 or anti-obesity medication in structured data or notes."),
             "pa": (P, "No PA weight-loss medication in structured data or notes.")},
    "prior_orlistat_stopped": {"glp1": (P, "No GLP-1 use."),
                               "pa": (P, "Orlistat stopped mid-2024; not concurrent.")},
    "med_list_absent": {"glp1": (I, "Medication list not reconciled/obtained; concurrent use cannot be confirmed."),
                        "pa": (I, "Medication list not reconciled/obtained.")},
    "status_unknown": {"glp1": (I, "Outside semaglutide injection with unknown current status (structured status 'unknown'; patient unsure)."),
                       "pa": (I, "Unnamed outside weight-loss injection with unknown status.")},
    "ozempic_structured_active_note_stopped": {
        "glp1": (P, "Structured Ozempic order still 'active' (2025-10) but newer explicit note (2026-08) says stopped ~2 months ago; newer explicit evidence wins."),
        "pa": (P, "Ozempic is not on the PA weight-loss list; no other agents.")},
    "stale_wegovy_old_list": {
        "glp1": (P, "Stale 2023 Wegovy statement never closed; current (2026-08) medication review lists no GLP-1; newer explicit evidence wins."),
        "pa": (P, "Same: current reconciliation lists no weight-loss medication.")},
    "note_bmi_30_4": {"glp1": (P, "No GLP-1 use."), "pa": (P, "No weight-loss medication.")},
    "latest_bmi_29_8": {"glp1": (P, "No GLP-1 use."), "pa": (P, "No weight-loss medication.")},
    "zepbound_discontinued_recent_fill": {
        "glp1": (C, "Phone note (2026-06) says Zepbound discontinued, but a pharmacy dispense on 2026-08-06 is newer — structured evidence newer than narrative."),
        "pa": (C, "Same Zepbound conflict (Zepbound is on the PA weight-loss list).")},
    "old_glp1": {"glp1": (P, "Liraglutide stopped in 2024; not concurrent."),
                 "pa": (P, "Saxenda stopped in 2024; not concurrent.")},
    "ambiguous_med_status": {"glp1": (I, "Patient unsure whether still taking a telehealth 'weight-loss shot'."),
                             "pa": (I, "Unknown weight-loss injection status.")},
}

COMORBIDITY_KEYS = ("hypertension", "dyslipidemia", "prediabetes")


def comorbidity_truth(conditions: dict) -> tuple[str, str]:
    """Status of 'has a qualifying weight-related comorbidity' (examples lists are non-exhaustive)."""
    present = [k for k in COMORBIDITY_KEYS if conditions.get(k) is True]
    if present and conditions.get("condition_status") == "resolved":
        return "FAIL", f"{', '.join(present)} documented as resolved (off treatment, normal BP)."
    if present:
        narrative = conditions.get("structured_condition_present") is False
        return "PASS", f"{', '.join(present)} documented" + (" (narrative only, no structured Condition)." if narrative else ".")
    if any(k in conditions and conditions[k] is None for k in COMORBIDITY_KEYS):
        return "CONFLICT", "Repeatedly elevated BP without a hypertension diagnosis."
    return "FAIL", "No weight-related comorbidity."

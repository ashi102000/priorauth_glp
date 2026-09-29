"""Scenario registry: how each cohort documentation_state / medication_scenario is realized.

Generator-only module. Nothing here may be imported by model-facing code.
Descriptions state the INTENDED chart pattern; note plans (generate_plans.py) implement it.
"""

# documentation_state -> intended chart pattern (weight-management history)
DOC_STATES: dict[str, str] = {
    # complete programs of stated length (start note, periodic follow-ups, inadequate response)
    "complete_6_5_months": "Structured diet+exercise program started ~6.5 mo before index; follow-ups; weight plateau.",
    "complete_7_months": "Structured program ~7 mo; follow-ups; inadequate response.",
    "complete_8_months": "Structured program ~8 mo; follow-ups; inadequate response.",
    "complete_9_months": "Structured program ~9 mo; follow-ups; inadequate response.",
    "complete_10_months": "Structured program ~10 mo; follow-ups; inadequate response.",
    "complete_11_months": "Structured program ~11 mo; follow-ups; inadequate response.",
    "complete_12_months": "Structured program ~12 mo; follow-ups; inadequate response.",
    "complete_14_months": "Structured program ~14 mo; follow-ups; inadequate response.",
    # missing evidence
    "absent": "No weight-management documentation at all; only unrelated visits.",
    "counseling_only": "Single brief 'discussed diet and exercise' counseling line; no program, no follow-up.",
    "diet_only": "Dietary changes documented over time; no exercise component.",
    "exercise_only": "Exercise routine documented over time; no dietary component.",
    "program_no_duration": "Enrolled in program, but no dates/duration recoverable (undated references only).",
    "start_no_followup": "Program start documented; no subsequent follow-up notes.",
    "complete_response_missing": "Program ~8 mo with follow-ups, but no statement about weight response/plateau.",
    # ambiguous
    "several_months": "Notes say 'past several months' of lifestyle efforts; no start date.",
    "long_standing_vague": "'Long-standing' / 'has tried dieting for years' — no dated structured program.",
    "exact_6_months": "Program start exactly 6 months before the continuation note (boundary).",
    "jan_start_july_followup": "Start note in Jan 2026, next relevant note late July 2026; duration must be inferred from dates.",
    "fragmented_multi_note": "Diet, exercise, follow-up, and response each in different notes (aggregation).",
    "intermittent_program": "Program started, lapsed, resumed; continuity unclear.",
    "complete_limited_improvement": "8-mo program; response described as 'modest/limited improvement' (response semantics ambiguous).",
    # hard
    "jan_start_feb_stop": "Program started Jan, stopped Feb (~1.5 mo), later notes mention 'tried diet earlier this year'.",
    "jan_mar_restart_july": "Started Jan, stopped Mar, restarted Jul — ~5 mo total, non-continuous.",
    "pcp_8mo_dietitian_3mo": "PCP notes say 8 mo of efforts; dietitian notes say enrolled only 3 mo ago (source contradiction).",
    "negated_structured_program": "Heavy weight-mgmt vocabulary but patient declined/never enrolled in program (negation trap).",
    "clear_then_stopped_6_weeks": "Clear program start; later note: stopped after ~6 weeks (later evidence reversal).",
    "buried_across_many_notes": "8-mo program evidence scattered as single sentences across many long unrelated notes.",
    "one_relevant_many_distractors": "Only one note carries the program evidence; many distractor notes.",
    "contradictory_program_dates": "Two notes give conflicting program start dates (one >=6 mo, one <6 mo).",
    "ambiguous_lifestyle": "Vague lifestyle language ('trying to eat better, more active'); not clearly a program.",
}

# medication_scenario -> intended medication/data pattern.
# NOTE: note_bmi_30_4 and latest_bmi_29_8 are BMI data-conflict scenarios stored in this field by the spec.
MED_SCENARIOS: dict[str, str] = {
    "none": "No GLP-1/anti-obesity medication history; filler chronic meds only.",
    "prior_orlistat_stopped": "Orlistat previously prescribed, stopped (GI intolerance) >6 mo before index.",
    "med_list_absent": "No MedicationStatement/Request resources for anti-obesity meds; med list sparse/absent.",
    "status_unknown": "Anti-obesity med mentioned in history with unknown current status.",
    "ozempic_structured_active_note_stopped": "MedicationRequest Ozempic status=active; recent note says patient stopped it.",
    "stale_wegovy_old_list": "Old Wegovy MedicationStatement (2+ yrs ago) never closed out; no recent fills.",
    "note_bmi_30_4": "Structured latest BMI 29.7; a clinic note states BMI 30.4 (structured vs narrative conflict).",
    "latest_bmi_29_8": "Earlier BMIs >=30; most recent structured BMI 29.8 (longitudinal conflict).",
    "zepbound_discontinued_recent_fill": "Zepbound documented discontinued, but a dispense/fill record is recent.",
    "old_glp1": "GLP-1 (liraglutide) used and stopped ~2 yrs ago.",
    "ambiguous_med_status": "Note says 'was on a weight-loss shot, not sure if still taking'.",
}

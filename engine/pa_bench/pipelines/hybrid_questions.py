"""Jev question sets for the hybrid pipeline (one fan-out request per PA case).

Design (docs.typesafe.ai, Jev 1.13 jaggedness): Jev only reads each note — event type, plan components,
stated start month/year, stated duration bucket, medication status. Code does all date arithmetic,
recency windows, duration, conflict detection and policy logic (hybrid_rules.py).

Option names are sent to the model: they must never coincide with hidden cohort vocabulary (the guard
enforces this; tests assert every generated request passes).
"""
from __future__ import annotations

from ..models.jev_provider import choice, noul

_NOT_MED = " Starting, planning, or taking a weight-loss medication (such as Wegovy) is not by itself a program or diet/exercise plan."
EVENT_OPTIONS = {
    "program_started": "The note documents that the patient starts, enrolls in, or is set up with a weight-management program or a structured diet/exercise plan at this time.",
    "program_ongoing": "The note documents that the patient is currently continuing an existing weight-management program or structured diet/exercise plan.",
    "program_stopped": "The note documents that the patient stopped, dropped out of, or lapsed from a weight-management program or plan and has not resumed it.",
    "program_restarted": "The note documents that the patient is restarting a weight-management program or plan after a break.",
    "declined_or_not_following": "The note documents that the patient declined or never enrolled in a program, or is currently not following any diet or exercise plan.",
    "informal_efforts_only": "The note documents only informal or vague diet/exercise efforts or intentions, or brief counseling, without a program or structured plan.",
    "past_efforts_only": "The note only refers to past diet/exercise attempts and does not say whether any are current.",
    "not_about_weight_management": "The note does not discuss the patient's diet, exercise, or weight-management program efforts (for example it only discusses medications or other problems).",
}
EVENT_OPTIONS = {k: (v + _NOT_MED if k in ("program_started", "program_ongoing", "program_restarted") else v)
                 for k, v in EVENT_OPTIONS.items()}
PARTICIPATION = ("program_started", "program_ongoing", "program_restarted")

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
YEARS = ["2023", "2024", "2025", "2026"]

DURATION_OPTIONS = {
    "under_6_months": "The note states the program or plan has lasted less than 6 months so far.",
    "6_months_or_more": "The note states the program or plan has lasted 6 months or longer.",
    "vague_duration": "The note describes the duration only vaguely (e.g., 'several months', 'for years', 'long-standing').",
    "not_stated": "The note does not state how long the program or plan has lasted.",
}

MED_OPTIONS = {
    "currently_taking": "The note says the patient is currently taking a GLP-1 receptor agonist or another weight-loss medication (not counting a newly planned Wegovy start).",
    "stopped": "The note says the patient stopped or is no longer taking such a medication.",
    "unclear_if_still_taking": "The note mentions such a medication but it is unclear whether the patient is still taking it.",
    "med_list_not_obtained": "The note says the patient's medication list could not be reviewed or obtained.",
    "reviewed_none": "The note documents a medication review that lists no GLP-1 or weight-loss medication.",
    "not_mentioned": "The note does not mention GLP-1 or weight-loss medication use, other than a newly planned Wegovy start.",
}

COMORB_OPTIONS = {
    "diagnosed_active": "The notes document a current diagnosis of hypertension, dyslipidemia/high cholesterol, type 2 diabetes, prediabetes, obstructive sleep apnea, or cardiovascular disease.",
    "resolved": "The notes document that such a condition existed but has resolved.",
    "suspected_not_diagnosed": "The notes mention elevated readings or concern (for example high blood pressure) without a diagnosis.",
    "none": "None of these conditions is documented.",
}

PROGRAM_CRITERIA = {"weight_management_program", "program_6_months", "lifestyle_adjunct", "adjunct_diet_and_activity"}
MED_CRITERIA = {"no_concurrent_glp1", "no_concurrent_pa_weight_loss_med"}


def note_questions(i: int, *, program: bool, temporal: bool, meds: bool) -> dict[str, dict]:
    n = f"`notes[{i}]`"
    q: dict[str, dict] = {}
    if program:
        q[f"event_{i}"] = choice(f"Which option best describes what {n} documents about the patient's weight-management program or diet/exercise plan?", EVENT_OPTIONS)
        q[f"diet_{i}"] = noul(f"Does {n} document the patient following, or being set up with, a reduced-calorie diet or structured eating plan?",
                              true="A reduced-calorie diet or structured eating plan is documented for the patient.",
                              false="No such diet or eating plan is documented in this note.")
        q[f"activity_{i}"] = noul(f"Does {n} document the patient following, or being set up with, a regular physical activity or exercise plan for weight management?",
                                  true="A regular physical activity or exercise plan for weight management is documented.",
                                  false="No such activity plan is documented (injury rehab exercises, one-off activities or asthma-related exercise do not count).")
        q[f"formal_{i}"] = noul(f"Does {n} refer to a formal weight-management program, dietitian-led plan, or coaching program (not only the patient's own efforts)?",
                                true="A formal program, dietitian-led plan, or coaching program is referred to.",
                                false="Only the patient's own efforts, or no program, are described.")
    if temporal:
        q[f"start_month_{i}"] = choice(f"If {n} states the month when the patient's weight-management program or plan BEGAN, and that is earlier than the note's own date, which month? Otherwise answer 'not_stated'.",
                                       {m: None for m in MONTHS} | {"not_stated": "The note does not state an earlier start month."})
        q[f"start_year_{i}"] = choice(f"If {n} states the year when the patient's weight-management program or plan BEGAN, and that start is earlier than the note's own date, which year? Otherwise answer 'not_stated'.",
                                      {y: None for y in YEARS} | {"not_stated": "The note does not state an earlier start year."})
        q[f"duration_{i}"] = choice(f"How does {n} describe how long the patient has been in the weight-management program or plan?", DURATION_OPTIONS)
    if meds:
        q[f"med_{i}"] = choice(f"What does {n} say about the patient's use of a GLP-1 receptor agonist or another weight-loss medication?", MED_OPTIONS)
    return q


def build_request(profile: dict, policy: dict, *, need_comorbidity: bool) -> tuple[dict, dict, list[dict]]:
    """Returns (state, questions, rows). rows[i] = the evidence chunk behind notes[i] (for provenance)."""
    crit_ids = {c["criterion_id"] for c in policy["criteria"]}
    wanted = (crit_ids & (PROGRAM_CRITERIA | MED_CRITERIA)) | ({"comorbidity"} if need_comorbidity else set())
    by_chunk: dict[str, dict] = {}
    for cid in sorted(wanted):
        for e in profile["evidence"].get(cid, []):
            row = by_chunk.setdefault(e["chunk_id"], {**e, "retrieved_for": set()})
            row["retrieved_for"].add(cid)
    rows = sorted(by_chunk.values(), key=lambda r: (r["date"], r["chunk_id"]))
    state = {"request_date": profile["request"]["request_date"],
             "notes": [{"date": r["date"], "note_type": r["note_type"], "text": r["text"]} for r in rows]}
    questions: dict[str, dict] = {}
    temporal = "program_6_months" in crit_ids
    for i, r in enumerate(rows):
        rf = r["retrieved_for"]
        questions |= note_questions(i, program=bool(rf & PROGRAM_CRITERIA), temporal=temporal and bool(rf & PROGRAM_CRITERIA),
                                    meds=bool(rf & MED_CRITERIA))
    if need_comorbidity:
        idx = [i for i, r in enumerate(rows) if "comorbidity" in r["retrieved_for"]]
        if idx:
            refs = ", ".join(f"`notes[{i}]`" for i in idx)
            questions["comorbidity"] = choice(f"Considering {refs}, which option best describes the patient's weight-related comorbid conditions?", COMORB_OPTIONS)
    for r in rows:
        r["retrieved_for"] = sorted(r["retrieved_for"])
    return state, questions, rows

"""Seeded chart-plan builder (generator-only; never imported by model-facing code).

A ChartPlan holds the structured resources, the note plans (facts each note must express), and the
hidden evidence annotations for one patient. Note TEXT is written separately (M1.3) from these plans.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import catalog as C

INDEX_DATE = date(2026, 9, 1)
WINDOW_START = date(2024, 9, 1)


def seed_for(pid: str) -> int:
    return int(hashlib.sha256(pid.encode()).hexdigest()[:12], 16)


def add_months(d: date, months: float) -> date:
    whole = int(months)
    frac_days = round((months - whole) * 30)
    y, m = divmod(d.month - 1 + whole, 12)
    year, month = d.year + y, m + 1
    day = min(d.day, [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day) + timedelta(days=frac_days)


def sub_months(d: date, months: float) -> date:
    whole = int(months)
    frac_days = round((months - whole) * 30)
    y, m = divmod(d.month - 1 - whole, 12)
    year, month = d.year + y, m + 1
    day = min(d.day, [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day) - timedelta(days=frac_days)


def A(concept: str, stance: str, relevance: bool = True, **facts) -> dict:
    """Hidden evidence annotation (concept-level). Stance is relative to 'the concept is satisfied'."""
    return {
        "criterion_id": concept,
        "relevance": relevance,
        "stance": stance,
        "facts": [{"predicate": k, "value": (v.isoformat() if isinstance(v, date) else v)} for k, v in facts.items()],
    }


@dataclass
class Note:
    date: date
    setting: str
    role: str                      # scenario role, e.g. program_start / distractor / final_request
    facts: list[str]
    anns: list[dict] = field(default_factory=list)
    vitals: bool = False
    length: str = "medium"         # short | medium | long
    trap: bool = False
    doc_id: str = ""
    encounter_id: str | None = None


class ChartBuilder:
    def __init__(self, p: dict):
        self.p = p
        self.pid = p["patient_id"]
        self.rng = random.Random(seed_for(self.pid))
        self.cls = p["benchmark_design"]["class"]
        self.ct = p["clinical_truth"]
        self.wm = self.ct["weight_management"]
        self.h_cm = p["anthropometrics"]["height_cm"]
        self.notes: list[Note] = []
        self.meds: list[dict] = []
        self.extra_obs: list[dict] = []
        self.response = "inadequate"   # weight trajectory profile
        self.last = INDEX_DATE - timedelta(days=self.rng.randint(10, 28))
        self.final: Note | None = None
        kcal = self.rng.choice([1400, 1500, 1600, 1800])
        self.diet = self.rng.choice(C.DIET_PLANS).format(kcal=kcal)
        self.exercise = self.rng.choice(C.EXERCISE_PLANS).format(days=self.rng.choice([3, 4, 5]))
        self.program = self.rng.choice(C.PROGRAM_NAMES)
        self.bmi_overrides: dict[date, float] = {}
        self.weight_overrides: dict[date, float] = {}
        self.decisions: list[str] = []
        self.extra_vitals_dates: list[date] = []
        female = p["demographics"]["sex"] == "female"
        self.she, self.her = ("she", "her") if female else ("he", "his")

    # ---------------- note helpers ----------------
    def note(self, d: date, setting: str, role: str, facts: list[str], anns=None, vitals=None, length="medium") -> Note:
        if vitals is None:
            vitals = setting in ("PCP", "APE")
        n = Note(d, setting, role, list(facts), list(anns or []), vitals, length)
        self.notes.append(n)
        return n

    def wt(self, d: date) -> str:
        return "{wt@" + d.isoformat() + "}"

    def final_note(self, d: date, facts: list[str], anns=None, length="medium") -> Note:
        facts = list(facts) + [
            "Plan: start semaglutide 2.4 mg weekly (Wegovy) with standard dose titration; counsel on GI side effects; recheck in 3 months."
        ]
        n = self.note(d, "PCP", "final_request", facts, anns, vitals=True, length=length)
        self.final = n
        return n

    # ---------------- program building blocks ----------------
    def start_note(self, d: date, setting="PCP", diet=True, exercise=True, referral=True, extra=None, anns_extra=None):
        facts = [f"Weight {self.wt(d)} kg today; patient wants to work on weight."] if setting == "PCP" else []
        anns = [A("weight_management_program", "SUPPORTS", program_event="start", event_date=d),
                A("program_duration", "SUPPORTS", program_event="start", event_date=d)]
        if diet:
            facts.append(f"Starting today: {self.diet}.")
            anns.append(A("diet", "SUPPORTS", diet_component=True))
        if exercise:
            facts.append(f"Activity plan: {self.exercise}.")
            anns.append(A("exercise", "SUPPORTS", exercise_component=True))
        if referral:
            facts.append(f"Enrolled in / referred to {self.program}; follow-up visits planned.")
        facts += extra or []
        anns += anns_extra or []
        return self.note(d, setting, "program_start", facts, anns)

    def nutrition_note(self, d: date, initial: bool, extra=None):
        if initial:
            facts = [f"Initial dietitian visit: reviewed food log, set plan — {self.diet}.",
                     "Reinforced activity goal: " + self.exercise + "."]
        else:
            facts = ["Dietitian follow-up: food log reviewed, adherent most days; small adjustments to snacks/portions.",
                     "Reports keeping up with activity plan."]
        facts += extra or []
        anns = [A("weight_management_program", "SUPPORTS", program_event="nutrition_visit", event_date=d),
                A("program_duration", "SUPPORTS", program_event="continuation", event_date=d),
                A("diet", "SUPPORTS", diet_component=True),
                A("exercise", "SUPPORTS", exercise_component=True)]
        return self.note(d, "NUTR", "program_nutrition", facts, anns, vitals=False)

    def followup_note(self, d: date, setting="PCP", extra=None):
        facts = ["Continues the diet and activity plan started earlier; reports good adherence most weeks."]
        if setting == "PCP":
            facts.insert(0, f"Weight {self.wt(d)} kg.")
        facts += extra or []
        anns = [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=d),
                A("program_duration", "SUPPORTS", program_event="continuation", event_date=d),
                A("diet", "SUPPORTS", diet_component=True),
                A("exercise", "SUPPORTS", exercise_component=True)]
        role = "program_followup"
        if setting in ("TEL", "MSG"):
            return self.note(d, setting, role, facts, anns, vitals=False, length="short")
        return self.note(d, setting, role, facts, anns)

    def response_facts(self, start: date, d: date, kind: str) -> tuple[list[str], list[dict]]:
        if kind == "inadequate":
            return ([f"Weight {self.wt(d)} kg vs {self.wt(start)} kg when the lifestyle plan began ({{pct@{start.isoformat()}@{d.isoformat()}}}% change) despite reported adherence; frustrated with plateau."],
                    [A("inadequate_response", "SUPPORTS", weight_response="inadequate")])
        if kind == "limited":
            return ([f"Weight {self.wt(d)} kg, down from {self.wt(start)} kg ({{pct@{start.isoformat()}@{d.isoformat()}}}% change). Some improvement, modest; patient would like more weight loss."],
                    [A("inadequate_response", "AMBIGUOUS", weight_response="modest_improvement")])
        return ([f"Weight {self.wt(d)} kg."], [])

    def complete_program(self, months: float, response="inadequate", start: date | None = None):
        last = self.last
        start = start or sub_months(last, months)
        self.start_note(start)
        self.nutrition_note(start + timedelta(days=self.rng.randint(12, 24)), initial=True)
        n_fu = 1 if months <= 7 else (2 if months < 12 else 3)
        span = (last - start).days
        for i in range(n_fu):
            d = start + timedelta(days=int(span * (i + 1) / (n_fu + 1)) + self.rng.randint(-6, 6))
            setting = ["PCP", "NUTR", "TEL"][i % 3] if n_fu > 1 else "PCP"
            if setting == "NUTR":
                self.nutrition_note(d, initial=False)
            else:
                self.followup_note(d, setting)
        rf, ra = self.response_facts(start, last, response)
        facts = ["Continues the diet and exercise plan; attends program follow-ups."] + rf
        anns = [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=last),
                A("program_duration", "SUPPORTS", program_event="continuation", event_date=last),
                A("diet", "SUPPORTS", diet_component=True), A("exercise", "SUPPORTS", exercise_component=True)] + ra
        self.final_note(last, facts, anns)
        self.response = {"inadequate": "inadequate", "limited": "limited", None: "inadequate"}[response]
        return start


# ---------------------------------------------------------------------------------------------
# documentation_state handlers
# ---------------------------------------------------------------------------------------------

def h_complete(months):
    def f(cb: ChartBuilder):
        cb.complete_program(months)
    return f


def h_absent(cb):
    cb.response = "flat"
    cb.final_note(cb.last, [f"Weight {cb.wt(cb.last)} kg. Here to discuss weight and medication options.",
                            "Do NOT mention any diet, exercise, lifestyle, or prior weight-loss attempts."])


def h_counseling_only(cb):
    d = date(2025, 11, cb.rng.randint(3, 20))
    cb.response = "gain"
    cb.note(d, "PCP", "counseling", [
        f"Weight {cb.wt(d)} kg, up about 3 kg over the past year.",
        "Brief counseling on healthy eating and increasing physical activity; printed handout given.",
        "No specific plan, program, or follow-up for weight arranged."],
        [A("weight_management_program", "NEUTRAL", program_event="counseling_only", event_date=d),
         A("program_duration", "NEUTRAL", program_event="counseling_only", event_date=d),
         A("diet", "SUPPORTS", diet_component="counseling"), A("exercise", "SUPPORTS", exercise_component="counseling"),
         A("inadequate_response", "SUPPORTS", weight_response="weight_gain")])
    cb.final_note(cb.last, [f"Weight {cb.wt(cb.last)} kg. Wants to discuss medication for weight.",
                            "Do NOT describe any interval diet/exercise efforts."])


def h_diet_only(cb):
    s = date(2025, 12, cb.rng.randint(2, 18))
    cb.response = "inadequate"
    na = lambda d, ev: [A("weight_management_program", "NEUTRAL", program_event=ev, event_date=d, components="diet_only"),
                        A("program_duration", "NEUTRAL", program_event=ev, event_date=d),
                        A("diet", "SUPPORTS", diet_component=True)]
    cb.note(s, "PCP", "diet_start", [f"Weight {cb.wt(s)} kg. Will start {cb.diet}.",
                                      "Do NOT mention exercise or physical activity at all."], na(s, "start"))
    m = date(2026, 4, cb.rng.randint(6, 24))
    cb.note(m, "PCP", "diet_followup", [f"Weight {cb.wt(m)} kg. Still tracking food intake; cut out soda.",
                                         "Do NOT mention exercise or physical activity."], na(m, "continuation"))
    cb.final_note(cb.last, [f"Continues dietary changes (food tracking) since December; weight {cb.wt(cb.last)} kg vs {cb.wt(s)} kg — little change.",
                            "Do NOT mention exercise or physical activity."],
                  na(cb.last, "continuation") + [A("inadequate_response", "SUPPORTS", weight_response="inadequate")])


def h_exercise_only(cb):
    s = date(2025, 12, cb.rng.randint(2, 18))
    cb.response = "inadequate"
    na = lambda d, ev: [A("weight_management_program", "NEUTRAL", program_event=ev, event_date=d, components="exercise_only"),
                        A("program_duration", "NEUTRAL", program_event=ev, event_date=d),
                        A("exercise", "SUPPORTS", exercise_component=True)]
    cb.note(s, "PCP", "exercise_start", [f"Weight {cb.wt(s)} kg. Plans to start {cb.exercise}.",
                                          "Do NOT mention diet, nutrition, or calorie intake at all."], na(s, "start"))
    m = date(2026, 4, cb.rng.randint(6, 24))
    cb.note(m, "PCP", "exercise_followup", [f"Weight {cb.wt(m)} kg. Keeping up exercise routine, enjoys it.",
                                             "Do NOT mention diet or nutrition."], na(m, "continuation"))
    cb.final_note(cb.last, [f"Regular exercise since December; weight {cb.wt(cb.last)} kg vs {cb.wt(s)} kg — minimal change.",
                            "Do NOT mention diet or nutrition."],
                  na(cb.last, "continuation") + [A("inadequate_response", "SUPPORTS", weight_response="inadequate")])


def h_program_no_duration(cb):
    cb.response = "inadequate"
    m = date(2026, 6, cb.rng.randint(8, 24))
    cb.note(m, "MSG", "program_mention_undated", [
        f"Portal message: patient asks whether the coaching session for {cb.program} can be moved to a different weekday.",
        "No dates of enrollment mentioned."],
        [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=m),
         A("program_duration", "AMBIGUOUS", program_event="undated_participation", event_date=m)], vitals=False, length="short")
    cb.final_note(cb.last, [
        f"Participating in {cb.program}; follows the program meal plan and exercise sessions (do NOT give any start date or duration).",
        f"Weight {cb.wt(cb.last)} kg, essentially unchanged from prior."],
        [A("weight_management_program", "SUPPORTS", program_event="participation_undated", event_date=cb.last),
         A("program_duration", "AMBIGUOUS", program_event="undated_participation", event_date=cb.last),
         A("diet", "SUPPORTS", diet_component=True), A("exercise", "SUPPORTS", exercise_component=True),
         A("inadequate_response", "SUPPORTS", weight_response="inadequate")])


def h_start_no_followup(cb):
    s = sub_months(cb.last, 8)
    cb.response = "flat"
    cb.start_note(s, extra=[f"Prior attempts at dieting on {cb.her} own over the years without sustained weight loss."],
                  anns_extra=[A("inadequate_response", "SUPPORTS", weight_response="prior_attempts_failed")])
    cb.final_note(cb.last, [f"Weight {cb.wt(cb.last)} kg. Interested in medication.",
                            "Do NOT mention the lifestyle program or any interval diet/exercise efforts."])


def h_complete_response_missing(cb):
    cb.complete_program(8, response=None)
    cb.decisions.append("Narrative never characterizes weight response; structured weights still exist (Phase 2: decide whether structured trend counts).")


def h_several_months(cb):
    cb.response = "inadequate"
    m = date(2026, 5, cb.rng.randint(4, 22))
    cb.note(m, "PCP", "vague_program", [f"Weight {cb.wt(m)} kg. Working on eating less fast food and walking more; continue.",
                                         "No start date given."],
            [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=m),
             A("program_duration", "AMBIGUOUS", program_event="undated_participation", event_date=m),
             A("diet", "SUPPORTS", diet_component=True), A("exercise", "SUPPORTS", exercise_component=True)])
    cb.final_note(cb.last, [f"Has been working on diet and exercise for the past several months; weight {cb.wt(cb.last)} kg, little change."],
                  [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=cb.last),
                   A("program_duration", "AMBIGUOUS", program_event="several_months", event_date=cb.last),
                   A("diet", "SUPPORTS", diet_component=True), A("exercise", "SUPPORTS", exercise_component=True),
                   A("inadequate_response", "SUPPORTS", weight_response="inadequate")])


def h_long_standing_vague(cb):
    cb.response = "flat"
    d = date(2025, 10, cb.rng.randint(6, 24))
    cb.note(d, "APE", "vague_history", ["Annual physical. Social history: has dieted on and off for years; walks the dog most days."],
            [A("weight_management_program", "SUPPORTS", program_event="long_standing_vague", event_date=d),
             A("program_duration", "AMBIGUOUS", program_event="long_standing_vague", event_date=d),
             A("diet", "SUPPORTS", diet_component="vague"), A("exercise", "SUPPORTS", exercise_component="vague")])
    cb.final_note(cb.last, [f"Long-standing efforts at diet and exercise; weight {cb.wt(cb.last)} kg, stable for years despite this.",
                            "No dates for any specific program."],
                  [A("weight_management_program", "SUPPORTS", program_event="long_standing_vague", event_date=cb.last),
                   A("program_duration", "AMBIGUOUS", program_event="long_standing_vague", event_date=cb.last),
                   A("inadequate_response", "SUPPORTS", weight_response="inadequate")])


def h_exact_6_months(cb):
    s, e = date(2026, 2, 18), date(2026, 8, 18)
    cb.last = e
    cb.start_note(s)
    cb.followup_note(date(2026, 5, 12), "PCP")
    rf, ra = cb.response_facts(s, e, "inadequate")
    cb.final_note(e, ["Continues the diet and activity plan started in February."] + rf,
                  [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=e),
                   A("program_duration", "SUPPORTS", program_event="continuation", event_date=e),
                   A("diet", "SUPPORTS", diet_component=True), A("exercise", "SUPPORTS", exercise_component=True)] + ra)


def h_jan_start_july_followup(cb):
    s, e = date(2026, 1, 20), date(2026, 7, 28)   # 189 days ~ 6.2 months
    cb.last = e
    cb.start_note(s)
    rf, ra = cb.response_facts(s, e, "inadequate")
    cb.final_note(e, ["Continues dietary modification and regular exercise initiated earlier this year (do not state the number of months)."] + rf,
                  [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=e),
                   A("program_duration", "SUPPORTS", program_event="continuation", event_date=e),
                   A("diet", "SUPPORTS", diet_component=True), A("exercise", "SUPPORTS", exercise_component=True)] + ra)


def h_fragmented(cb):
    s = sub_months(cb.last, 8)
    cb.note(s, "PCP", "fragment_referral", [f"Weight {cb.wt(s)} kg. Referred to dietitian for weight management; patient agreeable.",
                                             "Do NOT describe diet or exercise details in this note."],
            [A("weight_management_program", "SUPPORTS", program_event="start", event_date=s),
             A("program_duration", "SUPPORTS", program_event="start", event_date=s)])
    n = s + timedelta(days=cb.rng.randint(14, 25))
    cb.note(n, "NUTR", "fragment_diet", [f"Dietitian: set up {cb.diet}. Do NOT mention exercise."],
            [A("diet", "SUPPORTS", diet_component=True),
             A("weight_management_program", "SUPPORTS", program_event="nutrition_visit", event_date=n),
             A("program_duration", "SUPPORTS", program_event="continuation", event_date=n)], vitals=False)
    m = add_months(s, 4)
    cb.note(m, "MSG", "fragment_exercise", [f"Portal message from patient: update that they have been {cb.exercise} and feel better. Asks about protein intake."],
            [A("exercise", "SUPPORTS", exercise_component=True),
             A("program_duration", "SUPPORTS", program_event="continuation", event_date=m)], vitals=False, length="short")
    t = add_months(s, 6)
    cb.note(t, "TEL", "fragment_followup", ["RN telephone check-in on weight plan: still following dietitian meal plan and exercising; no barriers."],
            [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=t),
             A("program_duration", "SUPPORTS", program_event="continuation", event_date=t)], vitals=False, length="short")
    cb.final_note(cb.last, [f"Weight {cb.wt(cb.last)} kg vs {cb.wt(s)} kg at the time of dietitian referral ({{pct@{s.isoformat()}@{cb.last.isoformat()}}}% change).",
                            "Do NOT restate diet/exercise details or program length."],
                  [A("inadequate_response", "SUPPORTS", weight_response="inadequate")])


def h_intermittent(cb):
    s = date(2025, 10, cb.rng.randint(8, 20))
    cb.start_note(s)
    l = date(2026, 1, cb.rng.randint(6, 16))
    cb.note(l, "TEL", "program_lapse", ["Telephone: patient says they 'fell off' the meal plan over the holidays and has not been walking since Thanksgiving; will try to get back on track."],
            [A("weight_management_program", "CONTRADICTS", program_event="lapse", event_date=l),
             A("program_duration", "CONTRADICTS", program_event="lapse", event_date=l)], vitals=False, length="short")
    r = date(2026, 3, cb.rng.randint(3, 20))
    cb.note(r, "NUTR", "program_restart", [f"Dietitian: restarting meal plan after a break ({cb.diet}); resuming walking."],
            [A("weight_management_program", "SUPPORTS", program_event="restart", event_date=r),
             A("program_duration", "AMBIGUOUS", program_event="restart", event_date=r),
             A("diet", "SUPPORTS", diet_component=True), A("exercise", "SUPPORTS", exercise_component=True)], vitals=False)
    rf, ra = cb.response_facts(s, cb.last, "inadequate")
    cb.final_note(cb.last, ["On and off with the meal plan and walking since last fall; more consistent since spring."] + rf,
                  [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=cb.last),
                   A("program_duration", "AMBIGUOUS", program_event="intermittent", event_date=cb.last)] + ra)


def h_limited(cb):
    cb.complete_program(8, response="limited")


def h_jan_start_feb_stop(cb):
    s = date(2026, 1, 12)
    cb.start_note(s)
    cb.nutrition_note(date(2026, 1, 26), initial=True)
    st = date(2026, 2, 27)
    cb.note(st, "TEL", "program_stop", ["Telephone: patient stopped following the meal plan and stopped walking a few weeks ago due to work stress; cancelled dietitian follow-up; does not wish to reschedule now."],
            [A("weight_management_program", "CONTRADICTS", program_event="stop", event_date=st),
             A("program_duration", "CONTRADICTS", program_event="stop", event_date=st)], vitals=False, length="short")
    cb.final_note(cb.last, [f"Tried diet and exercise earlier this year without much success. Weight {cb.wt(cb.last)} kg."],
                  [A("weight_management_program", "AMBIGUOUS", program_event="retrospective_vague", event_date=cb.last),
                   A("program_duration", "AMBIGUOUS", program_event="retrospective_vague", event_date=cb.last),
                   A("inadequate_response", "SUPPORTS", weight_response="inadequate")])


def h_jan_mar_restart_july(cb):
    s, st, r, e = date(2026, 1, 2), date(2026, 3, 31), date(2026, 7, 1), date(2026, 8, 28)
    cb.last = e
    cb.start_note(s)
    cb.note(st, "MSG", "program_stop", ["Portal message: patient says they stopped going to the program and stopped the meal plan this month because of a family matter."],
            [A("weight_management_program", "CONTRADICTS", program_event="stop", event_date=st),
             A("program_duration", "CONTRADICTS", program_event="stop", event_date=st)], vitals=False, length="short")
    cb.note(r, "PCP", "program_restart", [f"Weight {cb.wt(r)} kg. Restarting the diet and walking plan today after a ~3-month break."],
            [A("weight_management_program", "SUPPORTS", program_event="restart", event_date=r),
             A("program_duration", "AMBIGUOUS", program_event="restart", event_date=r),
             A("diet", "SUPPORTS", diet_component=True), A("exercise", "SUPPORTS", exercise_component=True)])
    rf, ra = cb.response_facts(s, e, "inadequate")
    cb.final_note(e, ["Back on the diet and walking plan since July."] + rf,
                  [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=e),
                   A("program_duration", "AMBIGUOUS", program_event="continuation_after_gap", event_date=e)] + ra)


def h_pcp8_dietitian3(cb):
    v = date(2026, 1, 5)
    cb.note(v, "PCP", "vague_start", [f"Weight {cb.wt(v)} kg. Discussed diet and exercise; patient will try to cut portions and walk more."],
            [A("weight_management_program", "AMBIGUOUS", program_event="vague_start", event_date=v),
             A("program_duration", "AMBIGUOUS", program_event="vague_start", event_date=v)])
    d1 = date(2026, 5, 20)
    cb.note(d1, "NUTR", "dietitian_intake", [f"Initial dietitian visit. Patient reports no prior structured diet or exercise plan; this is {cb.her} first formal nutrition counseling. Plan: {cb.diet}; {cb.exercise}."],
            [A("weight_management_program", "SUPPORTS", program_event="start", event_date=d1),
             A("program_duration", "CONTRADICTS", program_event="start_reported_as_first", event_date=d1),
             A("diet", "SUPPORTS", diet_component=True), A("exercise", "SUPPORTS", exercise_component=True)], vitals=False)
    d2 = date(2026, 7, 15)
    cb.nutrition_note(d2, initial=False)
    cb.final_note(cb.last, ["Has completed 8 months of dedicated diet and exercise efforts since around the new year.",
                            f"Weight {cb.wt(cb.last)} kg, minimal change."],
                  [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=cb.last),
                   A("program_duration", "SUPPORTS", program_event="claimed_8_months", event_date=cb.last),
                   A("inadequate_response", "SUPPORTS", weight_response="inadequate")])


def h_negated(cb):
    cb.response = "flat"
    a = date(2025, 12, cb.rng.randint(1, 15))
    cb.note(a, "PCP", "program_declined", [
        f"Weight {cb.wt(a)} kg. Long discussion about weight management: structured weight-loss program, dietitian referral, meal replacement, exercise prescription.",
        "Patient declined enrollment in the structured weight management program and declined dietitian referral; prefers to manage on " + cb.her + " own."],
        [A("weight_management_program", "CONTRADICTS", program_event="declined", event_date=a)])
    b = date(2026, 3, cb.rng.randint(2, 20))
    cb.note(b, "TEL", "referral_noshow", ["Telephone: nutrition referral closed — patient did not schedule. Not enrolled in weight management program."],
            [A("weight_management_program", "CONTRADICTS", program_event="not_enrolled", event_date=b)], vitals=False, length="short")
    c = date(2026, 5, cb.rng.randint(4, 22))
    cb.note(c, "PCP", "no_regimen", [f"Weight {cb.wt(c)} kg. Weight management reviewed: no formal diet or exercise regimen at this time."],
            [A("weight_management_program", "CONTRADICTS", program_event="no_regimen", event_date=c),
             A("diet", "CONTRADICTS", diet_component=False), A("exercise", "CONTRADICTS", exercise_component=False)])
    cb.final_note(cb.last, [f"Weight {cb.wt(cb.last)} kg, unchanged since December. Weight-loss goals discussed again; still no structured diet or exercise program."],
                  [A("weight_management_program", "CONTRADICTS", program_event="no_program", event_date=cb.last),
                   A("inadequate_response", "SUPPORTS", weight_response="no_change")])


def h_clear_then_stopped(cb):
    cb.response = "gain"
    s = date(2026, 2, 9)
    cb.start_note(s)
    cb.nutrition_note(date(2026, 2, 23), initial=True)
    st = date(2026, 4, 6)
    cb.note(st, "PCP", "program_stop", [f"Weight {cb.wt(st)} kg. Stopped the diet and exercise program about 6 weeks in after an ankle injury; has not resumed."],
            [A("weight_management_program", "CONTRADICTS", program_event="stop", event_date=st),
             A("program_duration", "CONTRADICTS", program_event="stop", event_date=st)])
    cb.final_note(cb.last, [f"Weight {cb.wt(cb.last)} kg, up since spring. Not currently following a diet or exercise plan."],
                  [A("weight_management_program", "CONTRADICTS", program_event="not_active", event_date=cb.last),
                   A("inadequate_response", "SUPPORTS", weight_response="weight_gain")])


def h_buried(cb):
    s = sub_months(cb.last, 8)
    cb.note(s, "UC", "buried_start", [
        "LONG urgent care note for acute sinusitis (HPI, ROS, exam, plan).",
        f"One sentence only, inside social history: patient is starting {cb.program} this week — {cb.diet} and {cb.exercise}."],
        [A("weight_management_program", "SUPPORTS", program_event="start", event_date=s),
         A("program_duration", "SUPPORTS", program_event="start", event_date=s),
         A("diet", "SUPPORTS", diet_component=True), A("exercise", "SUPPORTS", exercise_component=True)], vitals=False, length="long")
    o = add_months(s, 2)
    cb.note(o, "ORTH", "buried_continuation", ["LONG orthopedic note for patellofemoral knee pain.",
                                                "One sentence only: remains in the weight program started in the winter, walking daily."],
            [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=o),
             A("program_duration", "SUPPORTS", program_event="continuation", event_date=o),
             A("exercise", "SUPPORTS", exercise_component=True)], vitals=False, length="long")
    l = add_months(s, 4)
    cb.note(l, "LAB", "buried_diet", ["LONG lab review note (CBC, CMP, lipids, vitamin D).",
                                       "One sentence only: reports adherence to the program meal plan."],
            [A("diet", "SUPPORTS", diet_component=True),
             A("program_duration", "SUPPORTS", program_event="continuation", event_date=l)], vitals=False, length="long")
    d = add_months(s, 6)
    cb.note(d, "DERM", "buried_exercise", ["LONG dermatology note for tinea versicolor.",
                                            "One sentence only: sweating more since exercising regularly with the weight program."],
            [A("exercise", "SUPPORTS", exercise_component=True),
             A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=d),
             A("program_duration", "SUPPORTS", program_event="continuation", event_date=d)], vitals=False, length="long")
    cb.final_note(cb.last, ["LONG multi-problem visit (reflux, sleep hygiene, knee pain follow-up).",
                            f"Weight {cb.wt(cb.last)} kg vs {cb.wt(s)} kg in the winter despite staying with the program ({{pct@{s.isoformat()}@{cb.last.isoformat()}}}% change)."],
                  [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=cb.last),
                   A("inadequate_response", "SUPPORTS", weight_response="inadequate")], length="long")


def h_one_relevant(cb):
    s = sub_months(cb.last, 8)
    cb.final_note(cb.last, [
        f"Weight history: {cb.wt(s)} kg in mid-December 2025 when {cb.she} started {cb.program}; today {cb.wt(cb.last)} kg.",
        f"Since mid-December {cb.she} has followed {cb.diet}, {cb.exercise}, with monthly program check-ins.",
        "Minimal weight change despite consistent adherence."],
        [A("weight_management_program", "SUPPORTS", program_event="summary", event_date=cb.last),
         A("program_duration", "SUPPORTS", program_event="summary_since", event_date=s),
         A("diet", "SUPPORTS", diet_component=True), A("exercise", "SUPPORTS", exercise_component=True),
         A("inadequate_response", "SUPPORTS", weight_response="inadequate")], length="long")
    # a weight observation exists at the program start date (no note that day)
    cb.extra_vitals_dates = [s]


def h_contradictory_dates(cb):
    p = date(2026, 6, cb.rng.randint(8, 22))
    cb.note(p, "PCP", "claim_nov_start", [f"Weight {cb.wt(p)} kg. Enrolled in a weight management program since November 2025 (diet + walking); continuing."],
            [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=p),
             A("program_duration", "SUPPORTS", program_event="claimed_start", event_date=date(2025, 11, 1))])
    n = date(2026, 7, cb.rng.randint(6, 24))
    cb.note(n, "NUTR", "claim_apr_start", [f"Dietitian follow-up: patient began the program in April 2026; reviewing {cb.diet}; walking most days."],
            [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=n),
             A("program_duration", "CONTRADICTS", program_event="claimed_start", event_date=date(2026, 4, 1)),
             A("diet", "SUPPORTS", diet_component=True), A("exercise", "SUPPORTS", exercise_component=True)], vitals=False)
    cb.final_note(cb.last, [f"Continues the program; weight {cb.wt(cb.last)} kg, minimal change."],
                  [A("weight_management_program", "SUPPORTS", program_event="continuation", event_date=cb.last),
                   A("inadequate_response", "SUPPORTS", weight_response="inadequate")])


def h_ambiguous_lifestyle(cb):
    cb.response = "flat"
    m = date(2026, 4, cb.rng.randint(4, 22))
    cb.note(m, "PCP", "vague_lifestyle", [f"Weight {cb.wt(m)} kg. Says {cb.she} is 'trying to eat better and be more active.'"],
            [A("weight_management_program", "AMBIGUOUS", program_event="vague_lifestyle", event_date=m),
             A("program_duration", "AMBIGUOUS", program_event="vague_lifestyle", event_date=m),
             A("diet", "AMBIGUOUS", diet_component="vague"), A("exercise", "AMBIGUOUS", exercise_component="vague")])
    cb.final_note(cb.last, [f"Lifestyle: 'doing what {cb.she} can' with food choices, busy schedule; some walking.",
                            f"Weight {cb.wt(cb.last)} kg, not much change."],
                  [A("weight_management_program", "AMBIGUOUS", program_event="vague_lifestyle", event_date=cb.last),
                   A("program_duration", "AMBIGUOUS", program_event="vague_lifestyle", event_date=cb.last),
                   A("inadequate_response", "SUPPORTS", weight_response="inadequate")])


DOC_HANDLERS = {
    "complete_6_5_months": h_complete(6.5), "complete_7_months": h_complete(7), "complete_8_months": h_complete(8),
    "complete_9_months": h_complete(9), "complete_10_months": h_complete(10), "complete_11_months": h_complete(11),
    "complete_12_months": h_complete(12), "complete_14_months": h_complete(14),
    "absent": h_absent, "counseling_only": h_counseling_only, "diet_only": h_diet_only, "exercise_only": h_exercise_only,
    "program_no_duration": h_program_no_duration, "start_no_followup": h_start_no_followup,
    "complete_response_missing": h_complete_response_missing, "several_months": h_several_months,
    "long_standing_vague": h_long_standing_vague, "exact_6_months": h_exact_6_months,
    "jan_start_july_followup": h_jan_start_july_followup, "fragmented_multi_note": h_fragmented,
    "intermittent_program": h_intermittent, "complete_limited_improvement": h_limited,
    "jan_start_feb_stop": h_jan_start_feb_stop, "jan_mar_restart_july": h_jan_mar_restart_july,
    "pcp_8mo_dietitian_3mo": h_pcp8_dietitian3, "negated_structured_program": h_negated,
    "clear_then_stopped_6_weeks": h_clear_then_stopped, "buried_across_many_notes": h_buried,
    "one_relevant_many_distractors": h_one_relevant, "contradictory_program_dates": h_contradictory_dates,
    "ambiguous_lifestyle": h_ambiguous_lifestyle,
}

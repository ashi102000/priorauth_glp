"""Deterministic composition of Jev note-level answers + structured features into criterion statuses.

All dates, windows, durations, recency comparisons and conflict checks happen here (never in a model).
Criterion confidence = min confidence over *decisive* Jev answers: an answer is decisive if replacing it
with its second-most-likely value changes the criterion status (uncertainty on unused branches is ignored).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..calc import whole_months_between
from ..policies.evaluator import CONFLICT, FAIL, INSUFFICIENT, PASS, eval_bmi
from .hybrid_questions import MONTHS, PARTICIPATION

GLP1_GENERICS = ["semaglutide", "liraglutide", "tirzepatide", "dulaglutide", "exenatide", "lixisenatide"]
PA_GENERICS = ["orlistat", "phentermine", "topiramate", "naltrexone", "bupropion", "benzphetamine", "diethylpropion",
               "phendimetrazine", "setmelanotide", "liraglutide", "semaglutide", "tirzepatide"]


# --------------------------------------------------------------------------------------------- answers
@dataclass
class Answers:
    """Resolved view over raw Jev answers, with single-answer flips for sensitivity analysis."""
    raw: dict
    flipped: frozenset = field(default_factory=frozenset)

    def has(self, key: str) -> bool:
        return key in self.raw

    def value(self, key: str):
        a = self.raw[key]
        if a["type"] == "noul":
            v = a["noul"] >= 0.5
            return (not v) if key in self.flipped else v
        ranked = sorted(a["probabilities"].items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[1][0] if key in self.flipped and len(ranked) > 1 else ranked[0][0]

    def confidence(self, key: str) -> float:
        a = self.raw[key]
        if a["type"] == "noul":
            return abs(2 * a["noul"] - 1)            # same scale as a binary Choice confidence
        return float(a["confidence"])

    def flip(self, key: str) -> "Answers":
        return Answers(self.raw, self.flipped | {key})


def with_confidence(rule, answers: Answers, keys: list[str]) -> tuple[str, float, list[str]]:
    """Criterion confidence = the highest confidence among the answers that would ALL have to be wrong for the
    status to change, found by flipping answers cumulatively from least to most confident (catches both a single
    decisive answer and several redundant weak ones). 1.0 if no combination of flips changes the status."""
    status = rule(answers)
    ranked = sorted((k for k in dict.fromkeys(keys) if answers.has(k) and answers.confidence(k) < 1.0),
                    key=lambda k: (answers.confidence(k), k))
    flipped = answers
    for n, k in enumerate(ranked, 1):
        flipped = flipped.flip(k)
        if rule(flipped) != status:
            prefix = ranked[:n]
            single = [x for x in prefix if rule(answers.flip(x)) != status]
            return status, answers.confidence(k), single or prefix
    return status, 1.0, []


# --------------------------------------------------------------------------------------------- context
@dataclass
class Ctx:
    rows: list[dict]               # evidence chunks, index == notes[i]
    request_date: date
    features: dict

    def idx(self, criterion_id: str) -> list[int]:
        return [i for i, r in enumerate(self.rows) if criterion_id in r["retrieved_for"]]

    def day(self, i: int) -> date:
        return date.fromisoformat(self.rows[i]["date"])


def keys_for(ctx: Ctx, criterion_id: str, kinds: tuple[str, ...]) -> list[str]:
    return [f"{k}_{i}" for i in ctx.idx(criterion_id) for k in kinds]


def _event(a: Answers, i: int) -> str | None:
    return a.value(f"event_{i}") if a.has(f"event_{i}") else None


def _yes(a: Answers, key: str) -> bool:
    return a.has(key) and bool(a.value(key))


# --------------------------------------------------------------------------------------------- program (FEP)
def rule_program_participation(ctx: Ctx, cid: str):
    idx = ctx.idx(cid)

    def rule(a: Answers) -> str:
        ev = {i: _event(a, i) for i in idx}
        part = [i for i, e in ev.items() if e in PARTICIPATION or e == "program_stopped"]
        formal = any(_yes(a, f"formal_{i}") for i in part) or (any(_yes(a, f"diet_{i}") for i in part)
                                                                 and any(_yes(a, f"activity_{i}") for i in part))
        if part and formal:
            return PASS
        if part:
            return INSUFFICIENT
        if any(e == "declined_or_not_following" for e in ev.values()):
            return FAIL
        return INSUFFICIENT
    return rule, keys_for(ctx, cid, ("event", "formal", "diet", "activity"))


# --------------------------------------------------------------------------------------------- adjunct (UHC / Aetna)
def rule_adjunct(ctx: Ctx, cid: str, params: dict, need_both: bool):
    window_start = ctx.request_date - timedelta(days=params.get("recency_window_days", 180))
    idx = [i for i in ctx.idx(cid) if ctx.day(i) >= window_start]

    def rule(a: Answers) -> str:
        rel = [i for i in idx if _event(a, i) not in (None, "not_about_weight_management")]
        if not rel:
            return INSUFFICIENT
        latest = max(ctx.day(i) for i in rel)
        last = [i for i in rel if ctx.day(i) == latest]
        events = {_event(a, i) for i in last}
        if events & set(PARTICIPATION):
            pool = [i for i in rel if _event(a, i) in PARTICIPATION or _event(a, i) == "informal_efforts_only"]
        elif events & {"program_stopped", "declined_or_not_following"}:
            return FAIL
        elif "informal_efforts_only" in events:
            pool = last
        else:                                   # past efforts only
            return INSUFFICIENT
        diet = any(_yes(a, f"diet_{i}") for i in pool)
        act = any(_yes(a, f"activity_{i}") for i in pool)
        formal = any(_yes(a, f"formal_{i}") for i in pool)
        ok = (diet and act) if need_both else (diet or act or (formal and bool(events & set(PARTICIPATION))))
        return PASS if ok else INSUFFICIENT
    return rule, keys_for(ctx, cid, ("event", "diet", "activity", "formal"))


# --------------------------------------------------------------------------------------------- 6-month program (Aetna)
def _declared_start(a: Answers, i: int, note_day: date) -> date | None:
    m = a.value(f"start_month_{i}") if a.has(f"start_month_{i}") else "not_stated"
    y = a.value(f"start_year_{i}") if a.has(f"start_year_{i}") else "not_stated"
    if m == "not_stated" or y == "not_stated":
        return None
    mi, yi = MONTHS.index(m) + 1, int(y)
    d = date(yi, mi, calendar.monthrange(yi, mi)[1])        # conservative: last day of the stated month
    return d if d < note_day else None


def rule_program_duration(ctx: Ctx, cid: str, params: dict):
    idx = ctx.idx(cid)
    min_months = params.get("min_duration_months", 6)

    def rule(a: Answers) -> str:
        ev = {i: _event(a, i) for i in idx}
        part = [i for i in idx if ev[i] in PARTICIPATION]
        stops = [i for i in idx if ev[i] in ("program_stopped", "declined_or_not_following")]
        if not part:
            return FAIL if any(ev[i] in ("declined_or_not_following", "program_stopped") for i in idx) else INSUFFICIENT
        # timeline -> segments
        order = {"program_started": 0, "program_restarted": 0, "program_ongoing": 1, "program_stopped": 2, "declined_or_not_following": 2}
        timeline = sorted((ctx.day(i), order[ev[i]], ev[i], i) for i in part + stops)
        segs, cur = [], None
        for d, _, e, i in timeline:
            if e in ("program_stopped", "declined_or_not_following"):
                if cur:
                    cur["end"], cur["stopped"] = d, True
                    segs.append(cur)
                    cur = None
                continue
            if cur is None:
                cur = {"start": d, "known": e != "program_ongoing", "end": d, "n": 1, "rows": [i], "stopped": False}
            elif e == "program_restarted":
                segs.append(cur)
                cur = {"start": d, "known": True, "end": d, "n": 1, "rows": [i], "stopped": False}
            else:
                cur["end"], cur["n"] = d, cur["n"] + 1
                cur["rows"].append(i)
        if cur:
            segs.append(cur)
        # declared starts ("since November 2025") and duration claims
        declared = sorted({ds for i in part if (ds := _declared_start(a, i, ctx.day(i)))})
        claims = {a.value(f"duration_{i}") for i in part if a.has(f"duration_{i}")}
        if declared and (declared[-1] - declared[0]).days > 62:
            return CONFLICT                                  # notes disagree about when the program began
        for s in segs:
            if declared:
                if not s["known"] and declared[0] <= s["start"]:
                    s["start"], s["known"], s["declared"] = declared[0], True, True
                elif s["known"] and (s["start"] - declared[0]).days > 62 and not s.get("declared"):
                    return CONFLICT                          # stated start much earlier than documented start
        known = [s for s in segs if s["known"]]
        dur = {id(s): whole_months_between(s["start"], s["end"]) for s in segs}
        best = max(known, key=lambda s: dur[id(s)], default=None)
        if best and "6_months_or_more" in claims and dur[id(best)] < min_months and not best["stopped"]:
            return CONFLICT                                  # claimed >= 6 months vs documented shorter participation
        diet = any(_yes(a, f"diet_{i}") for i in part)
        act = any(_yes(a, f"activity_{i}") for i in part)
        if best and dur[id(best)] >= min_months:
            follow = best["n"] >= 2 or best.get("declared", False)
            return PASS if (diet and act and follow) else INSUFFICIENT
        if len(known) > 1 and sum(dur[id(s)] for s in known) >= min_months:
            return CONFLICT                                  # >= 6 months in total but not continuous
        if best:
            if best["n"] == 1 and not best["stopped"] and len(known) == 1:
                return INSUFFICIENT                          # a start with no follow-up: duration unknowable
            return FAIL
        unknown = max(segs, key=lambda s: whole_months_between(s["start"], s["end"]))
        return PASS if (whole_months_between(unknown["start"], unknown["end"]) >= min_months and diet and act) else INSUFFICIENT
    return rule, keys_for(ctx, cid, ("event", "diet", "activity", "start_month", "start_year", "duration"))


# --------------------------------------------------------------------------------------------- medications (FEP)
def _drug_matches(text: str, names: list[str], generics: list[str]) -> bool:
    t = text.lower()
    return any(n.lower() in t for n in names) or any(g in t for g in generics)


def structured_med_assertions(features: dict, names: list[str], generics: list[str]) -> list[tuple[date, str, str]]:
    out = []
    for m in features["anti_obesity_medications"]:
        if not _drug_matches(m["text"], names, generics) or not m["date"]:
            continue
        d, st = date.fromisoformat(m["date"][:10]), m["status"]
        if m["resource_type"] == "MedicationDispense":
            kind = "active" if st == "completed" else "stopped"
        elif st in ("active", "on-hold", "intended"):
            kind = "active"
        elif st == "unknown":
            kind = "unknown"
        else:
            kind = "stopped"
        out.append((d, kind, "structured"))
    return out


NARRATIVE_KIND = {"currently_taking": "active", "stopped": "stopped", "unclear_if_still_taking": "unknown",
                  "med_list_not_obtained": "unknown", "reviewed_none": "none"}


def rule_concurrent_med(ctx: Ctx, cid: str, params: dict):
    names = params.get("glp1_list") or params.get("pa_weight_loss_list") or []
    generics = GLP1_GENERICS if "glp1_list" in params else PA_GENERICS
    structured = structured_med_assertions(ctx.features, names, generics)
    idx = ctx.idx(cid)

    def rule(a: Answers) -> str:
        narrative = [(ctx.day(i), NARRATIVE_KIND[v], "narrative") for i in idx
                     if a.has(f"med_{i}") and (v := a.value(f"med_{i}")) in NARRATIVE_KIND]
        allx = structured + narrative
        if not allx:
            return PASS
        latest = max(allx, key=lambda x: (x[0], x[2] == "narrative"))
        if latest[1] in ("stopped", "none"):
            return PASS
        if latest[1] == "unknown":
            return INSUFFICIENT
        if latest[2] == "structured" and any(k in ("stopped", "none") and s == "narrative" for _, k, s in allx):
            return CONFLICT                                   # newer structured record contradicts the narrative
        return FAIL
    return rule, [f"med_{i}" for i in idx]


# --------------------------------------------------------------------------------------------- comorbidity / BMI
def comorbidity_from(features: dict, a: Answers) -> tuple[str, str]:
    """Status of 'has a qualifying weight-related comorbidity' from structured Conditions + Jev narrative read."""
    conds = features["weight_related_conditions"]
    if any(c["clinical_status"] == "active" for c in conds):
        return PASS, "structured"
    resolved = any(c["clinical_status"] in ("resolved", "inactive", "remission") for c in conds)
    if not a.has("comorbidity"):
        return FAIL, "structured"
    v = a.value("comorbidity")
    if v == "diagnosed_active":
        return (CONFLICT if resolved else PASS), "jev"
    if v == "suspected_not_diagnosed":
        return CONFLICT, "jev"
    return FAIL, "jev"


def rule_bmi(ctx: Ctx, params: dict):
    latest = ctx.features["bmi"]["latest"]
    bmi = latest["value"] if latest else None

    def rule(a: Answers) -> str:
        comorb, _ = comorbidity_from(ctx.features, a)
        return eval_bmi(bmi, comorb, params)
    return rule, ["comorbidity"]


def needs_comorbidity(features: dict, params: dict) -> bool:
    latest = features["bmi"]["latest"]
    return bool(latest) and params["bmi_with_comorbidity"] <= latest["value"] < params["bmi_primary"] \
        and not any(c["clinical_status"] == "active" for c in features["weight_related_conditions"])


RULES = {
    "weight_management_program": lambda ctx, c: rule_program_participation(ctx, c["criterion_id"]),
    "lifestyle_adjunct": lambda ctx, c: rule_adjunct(ctx, c["criterion_id"], c["params"], need_both=False),
    "adjunct_diet_and_activity": lambda ctx, c: rule_adjunct(ctx, c["criterion_id"], c["params"], need_both=True),
    "program_6_months": lambda ctx, c: rule_program_duration(ctx, c["criterion_id"], c["params"]),
    "no_concurrent_glp1": lambda ctx, c: rule_concurrent_med(ctx, c["criterion_id"], c["params"]),
    "no_concurrent_pa_weight_loss_med": lambda ctx, c: rule_concurrent_med(ctx, c["criterion_id"], c["params"]),
}

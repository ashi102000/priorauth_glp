"""Hybrid composition rules on SYNTHETIC Jev answers (not cohort data) — exercises every rule path."""
from datetime import date

import pytest

from pa_bench.pipelines.hybrid_rules import (Answers, Ctx, comorbidity_from, rule_adjunct, rule_concurrent_med,
                                             rule_program_duration, rule_program_participation, with_confidence)

REQ = date(2026, 9, 1)


def ch(probs: dict):
    top = max(probs.values())
    n = len(probs)
    return {"type": "choice", "choice": max(probs, key=probs.get), "probabilities": probs,
            "confidence": max(0.0, (n * top - 1) / (n - 1))}


def nl(p):
    return {"type": "noul", "noul": p}


def ev(label, p=1.0, alt=None):
    alt = alt or ("not_about_weight_management" if label != "not_about_weight_management" else "informal_efforts_only")
    return ch({label: p, alt: round(1 - p, 6)}) if p < 1 else ch({label: 1.0, alt: 0.0})


def note(day, cids):
    return {"date": day, "retrieved_for": cids, "resource_id": f"DocumentReference/X-{day}", "chunk_id": f"X-{day}#c0"}


def ctx(days, cids, features=None):
    return Ctx(rows=[note(d, cids) for d in days], request_date=REQ,
               features=features or {"anti_obesity_medications": [], "weight_related_conditions": [], "bmi": {"latest": None}})


def prog(i, event, diet=0.9, act=0.9, formal=0.9, **extra):
    a = {f"event_{i}": ev(event), f"diet_{i}": nl(diet), f"activity_{i}": nl(act), f"formal_{i}": nl(formal)}
    for k, v in extra.items():
        a[f"{k}_{i}"] = v
    return a


def months(m="not_stated", y="not_stated", dur="not_stated"):
    return {"start_month": ch({m: 1.0, "not_stated" if m != "not_stated" else "January": 0.0}),
            "start_year": ch({y: 1.0, "not_stated" if y != "not_stated" else "2025": 0.0}),
            "duration": ch({dur: 1.0, "vague_duration" if dur != "vague_duration" else "not_stated": 0.0})}


# ---------------------------------------------------------------- FEP participation
@pytest.mark.parametrize("events,formal,expected", [
    (["program_started", "program_stopped"], 0.9, "PASS"),          # abandoned participation still counts (literal)
    (["declined_or_not_following"], 0.9, "FAIL"),
    (["informal_efforts_only"], 0.1, "INSUFFICIENT"),
    (["program_started"], 0.1, "INSUFFICIENT"),                      # 'program' with no formal/diet+activity signal
])
def test_participation(events, formal, expected):
    c = ctx([f"2026-0{i + 1}-10" for i in range(len(events))], ["weight_management_program"])
    raw = {}
    for i, e in enumerate(events):
        raw |= prog(i, e, diet=0.1 if formal < 0.5 else 0.9, act=0.1, formal=formal)
    rule, _ = rule_program_participation(c, "weight_management_program")
    assert rule(Answers(raw)) == expected


# ---------------------------------------------------------------- adjunct (recency window, latest statement)
def test_adjunct_paths():
    P = {"recency_window_days": 180}
    old = ctx(["2025-11-01"], ["lifestyle_adjunct"])                      # > 180 days before request
    r, _ = rule_adjunct(old, "lifestyle_adjunct", P, need_both=False)
    assert r(Answers(prog(0, "program_ongoing"))) == "INSUFFICIENT"
    c = ctx(["2026-04-01", "2026-08-01"], ["lifestyle_adjunct"])
    r, _ = rule_adjunct(c, "lifestyle_adjunct", P, need_both=False)
    assert r(Answers(prog(0, "program_ongoing") | prog(1, "declined_or_not_following"))) == "FAIL"   # latest wins
    assert r(Answers(prog(0, "program_stopped") | prog(1, "program_ongoing", diet=0.1, act=0.8, formal=0.1))) == "PASS"
    assert r(Answers(prog(0, "program_ongoing") | prog(1, "program_ongoing", diet=0.1, act=0.1, formal=0.1))) == "PASS"  # pool incl. earlier note
    assert r(Answers(prog(1, "past_efforts_only") | prog(0, "not_about_weight_management"))) == "INSUFFICIENT"
    r2, _ = rule_adjunct(c, "adjunct_diet_and_activity", P, need_both=True)
    c2 = ctx(["2026-04-01", "2026-08-01"], ["adjunct_diet_and_activity"])
    r2, _ = rule_adjunct(c2, "adjunct_diet_and_activity", P, need_both=True)
    assert r2(Answers(prog(0, "program_ongoing", act=0.1) | prog(1, "program_ongoing", act=0.1))) == "INSUFFICIENT"
    assert r2(Answers(prog(0, "program_ongoing") | prog(1, "program_ongoing"))) == "PASS"


# ---------------------------------------------------------------- 6-month duration (code does the arithmetic)
P6 = {"min_duration_months": 6}


def dur_rule(days):
    c = ctx(days, ["program_6_months"])
    return rule_program_duration(c, "program_6_months", P6)[0]


def with_m(i, event, **kw):
    a = prog(i, event)
    for k, v in months(**kw).items():
        a[f"{k}_{i}"] = v
    return a


def test_duration_exact_boundary_and_short():
    r = dur_rule(["2026-02-18", "2026-08-18"])
    assert r(Answers(with_m(0, "program_started") | with_m(1, "program_ongoing"))) == "PASS"
    r = dur_rule(["2026-02-18", "2026-08-17"])
    assert r(Answers(with_m(0, "program_started") | with_m(1, "program_ongoing"))) == "FAIL"


def test_duration_start_without_followup_is_insufficient():
    r = dur_rule(["2025-12-01"])
    assert r(Answers(with_m(0, "program_started"))) == "INSUFFICIENT"


def test_duration_interrupted_total_ge6_is_conflict_and_short_total_fail():
    r = dur_rule(["2025-10-01", "2026-01-10", "2026-03-10", "2026-08-15"])
    a = with_m(0, "program_started") | with_m(1, "program_stopped") | with_m(2, "program_restarted") | with_m(3, "program_ongoing")
    assert r(Answers(a)) == "CONFLICT"          # 3 + 5 months, never 6 continuous
    r = dur_rule(["2026-01-02", "2026-03-31", "2026-07-01", "2026-08-28"])
    a = with_m(0, "program_started") | with_m(1, "program_stopped") | with_m(2, "program_restarted") | with_m(3, "program_ongoing")
    assert r(Answers(a)) == "FAIL"              # 2 + 1 months


def test_duration_declared_start_paths():
    r = dur_rule(["2026-08-19"])
    assert r(Answers(with_m(0, "program_ongoing", m="December", y="2025"))) == "PASS"        # 'since December 2025'
    r = dur_rule(["2026-06-15", "2026-07-10"])
    a = with_m(0, "program_ongoing", m="November", y="2025") | with_m(1, "program_ongoing", m="April", y="2026")
    assert r(Answers(a)) == "CONFLICT"                                                      # disagreeing start dates
    r = dur_rule(["2026-05-20", "2026-08-10"])
    a = with_m(0, "program_started") | with_m(1, "program_ongoing", dur="6_months_or_more")
    assert r(Answers(a)) == "CONFLICT"                                                      # claim vs documented start
    r = dur_rule(["2026-06-01", "2026-08-01"])
    assert r(Answers(with_m(0, "program_ongoing") | with_m(1, "program_ongoing"))) == "INSUFFICIENT"  # undated, short
    r = dur_rule(["2026-03-01"])
    assert r(Answers(with_m(0, "declined_or_not_following"))) == "FAIL"


# ---------------------------------------------------------------- medication reconciliation
def med_ctx(meds, days):
    f = {"anti_obesity_medications": meds, "weight_related_conditions": [], "bmi": {"latest": None}}
    return ctx(days, ["no_concurrent_glp1"], f)


def m(text, rtype, status, day):
    return {"text": text, "resource_type": rtype, "status": status, "date": day, "resource_id": f"{rtype}/x"}


GLP = {"glp1_list": ["Ozempic", "Zepbound", "Wegovy"]}


def med(i, label):
    return {f"med_{i}": ch({label: 1.0, "not_mentioned" if label != "not_mentioned" else "stopped": 0.0})}


@pytest.mark.parametrize("meds,labels,expected", [
    ([m("Ozempic 0.5 mg", "MedicationRequest", "active", "2025-10-14")], ["stopped"], "PASS"),          # newer narrative wins
    ([m("Zepbound 5 mg pen", "MedicationDispense", "completed", "2026-08-06")], ["stopped"], "CONFLICT"),  # fill after 'stopped'
    ([], ["unclear_if_still_taking"], "INSUFFICIENT"),
    ([], ["med_list_not_obtained"], "INSUFFICIENT"),
    ([m("Ozempic 0.5 mg", "MedicationRequest", "active", "2025-10-14")], ["not_mentioned"], "FAIL"),   # uncontradicted active
    ([], ["not_mentioned"], "PASS"),
    ([m("Wegovy 1.7 mg", "MedicationStatement", "active", "2024-01-09")], ["reviewed_none"], "PASS"),  # stale list vs current review
])
def test_medications(meds, labels, expected):
    c = med_ctx(meds, ["2026-06-16"])
    rule, _ = rule_concurrent_med(c, "no_concurrent_glp1", GLP)
    assert rule(Answers(med(0, labels[0]))) == expected


# ---------------------------------------------------------------- comorbidity + sensitivity-based confidence
def test_comorbidity_sources():
    base = {"anti_obesity_medications": [], "bmi": {"latest": None}}
    assert comorbidity_from(base | {"weight_related_conditions": [{"clinical_status": "active"}]}, Answers({}))[0] == "PASS"
    res = base | {"weight_related_conditions": [{"clinical_status": "resolved"}]}
    assert comorbidity_from(res, Answers({"comorbidity": ch({"resolved": 1.0, "none": 0.0})}))[0] == "FAIL"
    assert comorbidity_from(res, Answers({"comorbidity": ch({"diagnosed_active": 1.0, "none": 0.0})}))[0] == "CONFLICT"
    none = base | {"weight_related_conditions": []}
    assert comorbidity_from(none, Answers({"comorbidity": ch({"suspected_not_diagnosed": 0.9, "none": 0.1})}))[0] == "CONFLICT"


def test_sensitivity_ignores_non_decisive_uncertainty():
    c = ctx(["2026-02-01", "2026-03-01"], ["weight_management_program"])
    rule, keys = rule_program_participation(c, "weight_management_program")
    raw = prog(0, "program_started", 1.0, 1.0, 1.0) | prog(1, "program_ongoing", 1.0, 1.0, 1.0)
    raw["event_1"] = ch({"program_ongoing": 0.55, "not_about_weight_management": 0.45})   # uncertain but redundant
    st, conf, decisive = with_confidence(rule, Answers(raw), keys)
    assert st == "PASS" and conf == 1.0 and decisive == []
    raw["event_0"] = ch({"program_started": 0.6, "not_about_weight_management": 0.4})     # now both uncertain
    st, conf, decisive = with_confidence(rule, Answers(raw), keys)
    assert st == "PASS" and conf == pytest.approx(0.2) and set(decisive) == {"event_0", "event_1"}   # both must be wrong
    raw["event_1"] = ev("program_ongoing")                                                  # one weak decisive answer
    st, conf, decisive = with_confidence(rule, Answers(raw), keys)
    assert st == "PASS" and conf == 1.0

"""Assemble a full per-patient chart plan + hidden evidence annotations (generator-only)."""
from __future__ import annotations

import re
from datetime import date, timedelta

from . import catalog as C
from .chart import A, INDEX_DATE, WINDOW_START, ChartBuilder, DOC_HANDLERS, Note

NOTE_TARGET = {
    "easy_positive": (10, 13), "easy_negative": (10, 13), "missing_evidence": (10, 14),
    "ambiguous": (11, 15), "hard": (14, 18),
}
TRAP_WEIGHT = {"easy_positive": 0.15, "easy_negative": 0.15, "missing_evidence": 0.25, "ambiguous": 0.35, "hard": 0.6}
MAX_VITALS_DATES = 6


# ---------------------------------------------------------------------------------------------
# medication scenarios
# ---------------------------------------------------------------------------------------------

def _first(cb: ChartBuilder, role_prefix: str) -> Note:
    for n in sorted(cb.notes, key=lambda n: n.date):
        if n.role.startswith(role_prefix):
            return n
    return cb.final


def med_scenario(cb: ChartBuilder, scen: str) -> None:
    pid = cb.pid
    if scen == "prior_orlistat_stopped":
        cb.meds.append({"id": f"{pid}-ORLISTAT", "resourceType": "MedicationStatement", "text": "orlistat 120 mg PO TID with meals",
                        "status": "completed", "effective_start": "2024-04-10", "effective_end": "2024-07-15",
                        "dateAsserted": "2024-07-15", "note": "Stopped due to GI side effects.",
                        "_ann": A("concurrent_aom", "SUPPORTS", drug="orlistat", drug_class="lipase_inhibitor", active=False)})
        n = _first(cb, "program_start")
        n.facts.append("Tried orlistat in spring 2024; stopped after about 3 months due to GI side effects.")
        n.anns.append(A("concurrent_aom", "SUPPORTS", drug="orlistat", active=False, stopped="2024-07"))
    elif scen == "med_list_absent":
        cb.no_routine_meds = True
        cb.final.facts.append("Medication list not reconciled today — patient did not bring list and pharmacy records were not available.")
        cb.final.anns.append(A("concurrent_aom", "AMBIGUOUS", med_list="not_obtained"))
        cb.decisions.append("No MedicationRequest/Statement resources other than the requested Wegovy order (med list absent by design).")
    elif scen == "status_unknown":
        cb.meds.append({"id": f"{pid}-OUTSIDE-GLP1", "resourceType": "MedicationStatement",
                        "text": "semaglutide weekly injection (outside prescriber) — dose unknown", "status": "unknown",
                        "effective_start": "2025-05-01", "dateAsserted": "2025-11-18", "note": "Patient-reported; outside clinic prescription.",
                        "_ann": A("concurrent_aom", "AMBIGUOUS", drug="semaglutide", drug_class="GLP-1 RA", active=None)})
        cb.final.facts.append("Reports being prescribed a weekly weight-loss injection by an outside clinic last year; unsure of the name and whether still filling it. Will request outside records.")
        cb.final.anns.append(A("concurrent_aom", "AMBIGUOUS", drug="GLP-1 RA (unnamed)", active=None))
    elif scen == "ozempic_structured_active_note_stopped":
        cb.meds.append({"id": f"{pid}-OZEMPIC", "resourceType": "MedicationRequest", "text": "Ozempic (semaglutide) 0.5 mg SC once weekly",
                        "status": "active", "intent": "order", "authoredOn": "2025-10-14",
                        "_ann": A("concurrent_aom", "CONTRADICTS", drug="semaglutide (Ozempic)", drug_class="GLP-1 RA", active=True, source="structured")})
        cb.final.facts.append("Stopped Ozempic about 2 months ago because of nausea and cost; not currently taking it.")
        cb.final.anns.append(A("concurrent_aom", "SUPPORTS", drug="semaglutide (Ozempic)", active=False, source="narrative"))
    elif scen == "stale_wegovy_old_list":
        cb.meds.append({"id": f"{pid}-WEGOVY-2023", "resourceType": "MedicationStatement", "text": "Wegovy (semaglutide) 1.7 mg SC once weekly",
                        "status": "active", "effective_start": "2023-11-20", "dateAsserted": "2024-01-09",
                        "_ann": A("concurrent_aom", "CONTRADICTS", drug="semaglutide (Wegovy)", drug_class="GLP-1 RA", active=True, source="structured_stale")})
        cb.final.facts.append("Current medications reviewed with patient: {routine_meds}. No other prescriptions or injections.")
        cb.final.anns.append(A("concurrent_aom", "SUPPORTS", med_reconciliation="no_glp1", source="narrative"))
    elif scen == "note_bmi_30_4":
        d = cb.last - timedelta(days=20)
        cb.note(d, "OSR", "outside_bmi", ["Scanned intake form from an outside weight-management clinic: height 172 cm, weight 89.9 kg (clothed), BMI 30.4."],
                [A("bmi", "NEUTRAL", bmi_value=30.4, source="narrative_outside")], vitals=False, length="short")
    elif scen == "latest_bmi_29_8":
        cb.bmi_conflict_041 = True
    elif scen == "zepbound_discontinued_recent_fill":
        cb.meds.append({"id": f"{pid}-ZEPBOUND", "resourceType": "MedicationRequest", "text": "Zepbound (tirzepatide) 5 mg SC once weekly",
                        "status": "stopped", "intent": "order", "authoredOn": "2026-02-10",
                        "_ann": A("concurrent_aom", "SUPPORTS", drug="tirzepatide (Zepbound)", drug_class="GIP/GLP-1 RA", active=False, source="structured_order")})
        cb.meds.append({"id": f"{pid}-ZEPBOUND-FILL-2026-08-06", "resourceType": "MedicationDispense", "text": "Zepbound (tirzepatide) 5 mg/0.5 mL pen, 4 pens",
                        "status": "completed", "whenHandedOver": "2026-08-06", "authorizingPrescription": f"{pid}-ZEPBOUND",
                        "_ann": A("concurrent_aom", "CONTRADICTS", drug="tirzepatide (Zepbound)", drug_class="GIP/GLP-1 RA", active=True, source="dispense")})
        t = date(2026, 6, 16)
        cb.note(t, "TEL", "med_stop", ["Telephone: patient reports discontinuing Zepbound this month due to cost; will not refill."],
                [A("concurrent_aom", "SUPPORTS", drug="tirzepatide (Zepbound)", active=False, source="narrative")], vitals=False, length="short")
    elif scen == "old_glp1":
        cb.meds.append({"id": f"{pid}-SAXENDA", "resourceType": "MedicationStatement", "text": "Saxenda (liraglutide) 3 mg SC daily",
                        "status": "completed", "effective_start": "2024-02-05", "effective_end": "2024-08-01", "dateAsserted": "2024-08-01",
                        "_ann": A("concurrent_aom", "SUPPORTS", drug="liraglutide", drug_class="GLP-1 RA", active=False)})
        cb.final.facts.append("Previously on liraglutide (Saxenda) in 2024, stopped after about 6 months due to nausea.")
        cb.final.anns.append(A("concurrent_aom", "SUPPORTS", drug="liraglutide", active=False))
    elif scen == "ambiguous_med_status":
        cb.final.facts.append("States was on 'a weight-loss shot' through a telehealth service; not sure whether still taking it; will check and call back.")
        cb.final.anns.append(A("concurrent_aom", "AMBIGUOUS", drug="unknown injectable", active=None))


# ---------------------------------------------------------------------------------------------
# main assembly
# ---------------------------------------------------------------------------------------------

def build_plan(p: dict) -> tuple[dict, list[dict]]:
    cb = ChartBuilder(p)
    cb.no_routine_meds = False
    cb.bmi_conflict_041 = False
    state = cb.wm["documentation_state"]
    DOC_HANDLERS[state](cb)
    med_scenario(cb, cb.ct["medication_scenario"])
    rng, pid = cb.rng, cb.pid

    # ---------- conditions ----------
    conds = cb.ct["conditions"]
    structured_ok = conds.get("structured_condition_present", True) is not False
    conditions, comorb = [], []   # comorb: (key, status) status in active|narrative_only|resolved|ambiguous
    for key in ("hypertension", "dyslipidemia", "prediabetes"):
        v = conds.get(key)
        if v is True:
            if key == "hypertension" and conds.get("condition_status") == "resolved":
                comorb.append((key, "resolved"))
            elif not structured_ok:
                comorb.append((key, "narrative_only"))
            else:
                comorb.append((key, "active"))
        elif v is None and key in conds:
            comorb.append((key, "ambiguous"))
    for key, status in comorb:
        if status in ("active", "resolved"):
            code, disp, suf = C.CONDITIONS[key]
            c = {"id": f"{pid}-{suf}", "code": code, "display": disp,
                 "clinical_status": "resolved" if status == "resolved" else "active",
                 "onset": f"{rng.randint(2018, 2023)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"}
            if status == "resolved":
                c["abatement"] = "2025-03-12"
            c["_ann"] = A("comorbidity", "CONTRADICTS" if status == "resolved" else "SUPPORTS", condition=key,
                          clinical_status=c["clinical_status"], source="structured")
            conditions.append(c)
    final_bmi_target = 29.8 if cb.bmi_conflict_041 else p["anthropometrics"]["current_bmi"]
    if final_bmi_target >= 30 or cb.bmi_conflict_041:
        code, disp, suf = C.CONDITIONS["obesity"]
    elif final_bmi_target >= 27:
        code, disp, suf = C.CONDITIONS["overweight"]
    else:
        code = None
    if code:
        conditions.append({"id": f"{pid}-{suf}", "code": code, "display": disp, "clinical_status": "active",
                           "onset": f"2024-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"})
    target_c = rng.randint(max(3, len(conditions) + 1), 8)
    fillers = rng.sample(C.FILLER_CONDITIONS, k=max(1, target_c - len(conditions)))
    for code, disp, suf in fillers:
        conditions.append({"id": f"{pid}-{suf}", "code": code, "display": disp, "clinical_status": "active",
                           "onset": f"{rng.randint(2015, 2024)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"})

    # ---------- routine meds ----------
    htn_med = rng.choice(C.CONDITION_MEDS["hypertension"])
    statin = rng.choice(C.CONDITION_MEDS["dyslipidemia"])
    routine = []
    if not cb.no_routine_meds:
        for key, status in comorb:
            if key == "hypertension" and status in ("active", "narrative_only"):
                routine.append(htn_med)
            if key == "dyslipidemia" and status in ("active", "narrative_only"):
                routine.append(statin)
        filler_map = {"ALLERGY": "cetirizine 10 mg PO daily PRN", "GERD": "omeprazole 20 mg PO daily", "VITD": "vitamin D3 2000 IU PO daily",
                      "LBP": "ibuprofen 400 mg PO PRN pain", "ANX": "sertraline 50 mg PO daily", "MIGRAINE": "sumatriptan 50 mg PO PRN migraine",
                      "ECZEMA": "triamcinolone 0.1% cream BID PRN"}
        for _, _, suf in fillers:
            if suf in filler_map:
                routine.append(filler_map[suf])
        while len(routine) < 2:
            extra = rng.choice(["fluticasone nasal spray 1 spray each nostril daily", "multivitamin PO daily", "melatonin 3 mg PO nightly PRN"])
            if extra not in routine:
                routine.append(extra)
    meds = []
    for i, text in enumerate(routine):
        slug = re.sub(r"[^A-Z0-9]", "", text.split(" ")[0].upper())[:12]
        otc = any(w in text for w in ("vitamin", "cetirizine", "multivitamin", "melatonin", "ibuprofen"))
        if otc:
            meds.append({"id": f"{pid}-{slug}", "resourceType": "MedicationStatement", "text": text, "status": "active",
                         "effective_start": f"{rng.randint(2020, 2024)}-{rng.randint(1, 12):02d}-01", "dateAsserted": "2026-01-15"})
        else:
            meds.append({"id": f"{pid}-{slug}", "resourceType": "MedicationRequest", "text": text, "status": "active",
                         "intent": "order", "authoredOn": f"{rng.randint(2021, 2025)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"})
    meds += cb.meds
    meds.append({"id": f"{pid}-WEGOVY-REQ", "resourceType": "MedicationRequest",
                 "text": "Wegovy (semaglutide) 0.25 mg SC once weekly x4 weeks, then titrate per label to 2.4 mg weekly",
                 "status": "draft", "intent": "order", "authoredOn": cb.last.isoformat(), "requested_drug": True})
    for n in cb.notes:
        n.facts = [f.replace("{routine_meds}", ", ".join(routine) if routine else "none") for f in n.facts]

    # ---------- distractors ----------
    lo, hi = NOTE_TARGET[cb.cls]
    if state in ("buried_across_many_notes", "one_relevant_many_distractors"):
        lo, hi = 18, 20
    target_notes = rng.randint(lo, hi)
    enc_target = rng.randint(5, 12)
    tw = TRAP_WEIGHT[cb.cls] if state not in ("buried_across_many_notes", "one_relevant_many_distractors") else 0.5
    n_distract = max(0, target_notes - len(cb.notes))
    n_trap = round(n_distract * tw)
    traps = [d for d in C.DISTRACTORS if d["trap"]]
    plain = [d for d in C.DISTRACTORS if not d["trap"]]
    rng.shuffle(traps)
    rng.shuffle(plain)
    rng.shuffle(plain)
    pool = traps[:n_trap] + plain   # quota traps first so the in-person encounter cap doesn't crowd them out
    pool += traps[n_trap:]   # traps beyond the quota are only used if plain distractors run out
    have_ape = any(n.setting == "APE" for n in cb.notes)
    used_dates = {n.date for n in cb.notes}

    def in_person_count():
        return sum(1 for n in cb.notes if C.SETTINGS[n.setting][3])

    def free_date(before: date | None = None) -> date:
        end = before or (INDEX_DATE - timedelta(days=5))
        for _ in range(500):
            d = WINDOW_START + timedelta(days=rng.randint(0, (end - WINDOW_START).days))
            if all(abs((d - u).days) > 2 for u in used_dates):
                return d
        raise RuntimeError("no free date")

    while len(cb.notes) < target_notes and pool:
        dt = None
        for i, cand in enumerate(pool):
            in_person = C.SETTINGS[cand["setting"]][3]
            if cand["setting"] == "APE" and have_ape:
                continue
            if in_person and in_person_count() >= enc_target:
                continue
            dt = pool.pop(i)
            break
        if dt is None:
            dt = pool.pop(0)   # allow exceeding encounter target rather than failing
            if dt["setting"] == "APE" and have_ape:
                continue
        is_ape = dt["setting"] == "APE"
        d = free_date(before=cb.last - timedelta(days=20) if is_ape else None)
        used_dates.add(d)
        anns = []
        if dt["trap"]:
            anns = [A(c, "NEUTRAL", relevance=False, hard_negative=True) for c in dt.get("trap_concepts", [])]
        facts = [dt["topic"][0].upper() + dt["topic"][1:] + "."]
        if is_ape:
            have_ape = True
            facts.append("Do NOT discuss diet, exercise, or weight-loss plans beyond recording vitals.")
        else:
            facts.append("Unrelated to weight management; do NOT mention weight-loss plans.")
        n = cb.note(d, dt["setting"], "distractor", facts, anns, vitals=is_ape,
                    length="long" if state in ("buried_across_many_notes", "one_relevant_many_distractors") and rng.random() < 0.5 else rng.choice(["short", "medium"]))
        n.trap = dt["trap"]
        n.topic = dt["topic"]

    cb.notes.sort(key=lambda n: n.date)

    # ---------- vitals dates & weights ----------
    vit_notes = [n for n in cb.notes if n.vitals]
    if len(vit_notes) < 3:
        for n in [n for n in cb.notes if n.role == "distractor" and n.setting in ("UC", "IMM", "ORTH", "DERM") and n.date < cb.last]:
            if len([m for m in cb.notes if m.vitals]) >= 3:
                break
            n.vitals = True
        vit_notes = [n for n in cb.notes if n.vitals]
    if len(vit_notes) > MAX_VITALS_DATES:
        droppable = [n for n in vit_notes if n.role == "distractor"]
        for n in droppable[: len(vit_notes) - MAX_VITALS_DATES]:
            n.vitals = False
            n.facts.append("Vitals not recorded in this note.")
        vit_notes = [n for n in cb.notes if n.vitals]
    token_dates = {date.fromisoformat(m) for n in cb.notes for f in n.facts for m in re.findall(r"\{(?:wt|pct)@(\d{4}-\d{2}-\d{2})", f)}
    token_dates |= {date.fromisoformat(m) for n in cb.notes for f in n.facts for m in re.findall(r"@\d{4}-\d{2}-\d{2}@(\d{4}-\d{2}-\d{2})\}", f)}
    note_dates_all = {n.date for n in cb.notes}
    for d in token_dates - {n.date for n in vit_notes}:
        if d not in note_dates_all and d not in cb.extra_vitals_dates:
            cb.extra_vitals_dates.append(d)
    vit_dates = sorted({n.date for n in vit_notes} | set(cb.extra_vitals_dates) | token_dates)
    h2 = (cb.h_cm / 100) ** 2
    w_end = round(29.8 * h2, 1) if cb.bmi_conflict_041 else p["anthropometrics"]["current_weight_kg"]
    prog_start = next((n.date for n in cb.notes if n.role in ("program_start", "fragment_referral", "buried_start", "diet_start",
                                                              "exercise_start", "program_declined", "vague_start", "counseling")), vit_dates[0])
    prof = cb.response
    if prof == "inadequate":
        w_s = w_end * (1 + rng.uniform(0.012, 0.035))
    elif prof == "limited":
        w_s = w_end * 1.047
    elif prof == "gain":
        w_s = w_end * (1 - rng.uniform(0.025, 0.04))
    else:
        w_s = w_end * (1 + rng.uniform(-0.008, 0.008))
    weights = {}
    t_end = vit_dates[-1]
    for d in vit_dates:
        if d <= prog_start:
            w = w_s * (1 + rng.uniform(-0.012, 0.012)) if d != prog_start else w_s
        else:
            frac = (d - prog_start).days / max(1, (t_end - prog_start).days)
            w = w_s + (w_end - w_s) * frac + (rng.uniform(-0.35, 0.35) if d != t_end else 0)
        weights[d] = w
    weights[t_end] = w_end
    final_bmi = p["anthropometrics"]["current_bmi"] if not cb.bmi_conflict_041 else 29.8
    # keep historical BMIs on the same side of 27 and 30 as the final (except the designed conflict, GLP1-041)
    for d in vit_dates[:-1]:
        b = weights[d] / h2
        for thr in (27.0, 30.0):
            if final_bmi < thr <= b + 0.05:
                weights[d] = (thr - 0.15) * h2
            elif final_bmi >= thr and b < thr + 0.05:
                weights[d] = (thr + 0.15) * h2
    if cb.bmi_conflict_041 and len(vit_dates) >= 2:
        weights[vit_dates[-2]] = p["anthropometrics"]["current_weight_kg"]   # 92.8 kg -> BMI 30.3
        for d in vit_dates[:-2]:
            weights[d] = max(weights[d], 30.4 * h2)
        cb.decisions.append("BMI series: penultimate 30.3, latest 29.8 (DECISIONS.md M1.1).")
    weights = {d: round(w, 1) for d, w in weights.items()}
    bmis = {d: round(w / h2, 1) for d, w in weights.items()}
    bmis[t_end] = final_bmi
    if cb.bmi_conflict_041 and len(vit_dates) >= 2:
        bmis[vit_dates[-2]] = 30.3

    has_htn = any(k == "hypertension" and s in ("active", "narrative_only") for k, s in comorb)
    htn_amb = any(k == "hypertension" and s == "ambiguous" for k, s in comorb)
    bps = {}
    for d in vit_dates:
        if has_htn:
            bps[d] = (rng.randint(126, 142), rng.randint(78, 90))
        elif htn_amb:
            bps[d] = (rng.randint(132, 139), rng.randint(84, 89))
        else:
            bps[d] = (rng.randint(108, 126), rng.randint(66, 80))

    # ---------- labs ----------
    has_dys = any(k == "dyslipidemia" and s in ("active", "narrative_only") for k, s in comorb)
    lab_date = next((n.date for n in cb.notes if n.vitals and n.date < t_end), t_end)
    labs = {}
    a1c = round(rng.uniform(5.8, 6.2), 1) if any(k == "prediabetes" for k, _ in comorb) else round(rng.uniform(4.9, 5.6), 1)
    labs["A1C"] = (lab_date, a1c)
    if has_dys:
        labs["LDL"], labs["HDL"], labs["TG"] = (lab_date, rng.randint(152, 186)), (lab_date, rng.randint(36, 46)), (lab_date, rng.randint(170, 260))
    elif rng.random() < 0.5:
        labs["LDL"], labs["HDL"], labs["TG"] = (lab_date, rng.randint(88, 124)), (lab_date, rng.randint(45, 65)), (lab_date, rng.randint(80, 145))
    for n in cb.notes:
        if n.role == "distractor" and n.setting == "LAB":
            if "vitamin D" in n.topic:
                v = rng.randint(24, 34)
                labs["VITD"] = (n.date, v)
                n.facts.append(f"25-OH vitamin D {v} ng/mL.")
            elif "TSH" in n.topic:
                v = round(rng.uniform(0.9, 3.2), 2)
                labs["TSH"] = (n.date, v)
                n.facts.append(f"TSH {v} mIU/L.")
            elif "lipid" in n.topic and "LDL" in labs:
                n.facts.append(f"LDL {labs['LDL'][1]}, HDL {labs['HDL'][1]}, TG {labs['TG'][1]} mg/dL.")
                for k in ("LDL", "HDL", "TG"):   # the panel was resulted on the lab-review date
                    labs[k] = (n.date, labs[k][1])

    # ---------- comorbidity mentions in PCP/APE notes ----------
    def comorb_line(key, status, d):
        bp = bps.get(d)
        bp_s = f"{bp[0]}/{bp[1]}" if bp else "at goal"
        if key == "hypertension" and status in ("active", "narrative_only"):
            return (f"Hypertension: BP {bp_s} on {htn_med}; continue.", A("comorbidity", "SUPPORTS", condition="hypertension", source="narrative"))
        if key == "hypertension" and status == "resolved":
            return ("History of hypertension, resolved after lifestyle changes; off amlodipine since early 2025 with normal home and office readings.",
                    A("comorbidity", "CONTRADICTS", condition="hypertension", clinical_status="resolved", source="narrative"))
        if key == "hypertension" and status == "ambiguous":
            return (f"BP {bp_s} today, above goal; no prior diagnosis of hypertension. Recheck at next visit.",
                    A("comorbidity", "AMBIGUOUS", condition="hypertension", source="narrative"))
        if key == "dyslipidemia":
            ldl = labs.get("LDL", (None, "elevated"))[1]
            if status == "narrative_only":
                return (f"High cholesterol — LDL {ldl} on last panel; on {statin}.", A("comorbidity", "SUPPORTS", condition="dyslipidemia", source="narrative"))
            return (f"Hyperlipidemia on {statin}; last LDL {ldl}.", A("comorbidity", "SUPPORTS", condition="dyslipidemia", source="narrative"))
        if key == "prediabetes":
            return (f"A1c {a1c}% — prediabetes range.", A("comorbidity", "SUPPORTS", condition="prediabetes", source="narrative"))
        return None

    for n in cb.notes:
        if n.setting not in ("PCP", "APE") or not comorb:
            continue
        if n is cb.final or rng.random() < 0.5 or (n.role == "distractor" and n.setting == "APE"):
            for key, status in comorb:
                r = comorb_line(key, status, n.date)
                if r:
                    n.facts.append(r[0])
                    n.anns.append(r[1])

    # ---------- IDs + encounters ----------
    counters: dict[str, int] = {}
    encounters = []
    for n in cb.notes:
        counters[n.setting] = counters.get(n.setting, 0) + 1
        n.doc_id = f"{pid}-{n.setting}-{counters[n.setting]:03d}"
        if C.SETTINGS[n.setting][3]:
            eid = f"{pid}-ENC-{n.date.isoformat()}"
            n.encounter_id = eid
            if not any(e["id"] == eid for e in encounters):
                encounters.append({"id": eid, "date": n.date.isoformat(), "type": C.SETTINGS[n.setting][0], "setting": n.setting})
    note_dates = {n.date for n in cb.notes}
    for d in cb.extra_vitals_dates:
        if d not in note_dates:
            encounters.append({"id": f"{pid}-ENC-{d.isoformat()}", "date": d.isoformat(), "type": "Nurse visit — weight check", "setting": "RN"})
    k = 0
    while len(encounters) < 5:
        d = free_date(before=cb.last)
        used_dates.add(d)
        encounters.append({"id": f"{pid}-ENC-{d.isoformat()}", "date": d.isoformat(),
                           "type": ["Lab draw", "Nurse visit — BP check", "Lab draw"][k % 3], "setting": "RN"})
        k += 1
    encounters.sort(key=lambda e: e["date"])
    enc_by_date = {e["date"]: e["id"] for e in encounters}

    # ---------- observations ----------
    obs = [{"id": f"{pid}-HT-{vit_dates[0].isoformat()}", "key": "HT", "date": vit_dates[0].isoformat(), "value": cb.h_cm}]
    for d in vit_dates:
        ds = d.isoformat()
        obs.append({"id": f"{pid}-WT-{ds}", "key": "WT", "date": ds, "value": weights[d]})
        obs.append({"id": f"{pid}-BMI-{ds}", "key": "BMI", "date": ds, "value": bmis[d]})
        if d in bps and d not in cb.extra_vitals_dates:
            obs.append({"id": f"{pid}-BP-{ds}", "key": "BP", "date": ds, "systolic": bps[d][0], "diastolic": bps[d][1]})
    for key, (d, v) in labs.items():
        obs.append({"id": f"{pid}-{key}-{d.isoformat()}", "key": key, "date": d.isoformat(), "value": v})
    fill_date = vit_dates[0].isoformat()
    for key, val in (("TSH", round(rng.uniform(0.9, 3.2), 2)), ("VITD", rng.randint(24, 40)),
                     ("LDL", rng.randint(88, 124)), ("HDL", rng.randint(45, 65)), ("TG", rng.randint(80, 145))):
        if len(obs) >= 10:
            break
        if not any(o["key"] == key for o in obs):
            obs.append({"id": f"{pid}-{key}-{fill_date}", "key": key, "date": fill_date, "value": val})
    while len(obs) > 20:
        drop = next((o for o in obs if o["key"] == "BP" and o["date"] != t_end.isoformat()), None) or \
               next(o for o in obs if o["key"] in ("HDL", "TG"))
        obs.remove(drop)
    for o in obs:
        o["encounter_id"] = enc_by_date.get(o["date"])

    # ---------- resolve tokens in facts ----------
    def resolve(s: str) -> str:
        s = re.sub(r"\{wt@(\d{4}-\d{2}-\d{2})\}", lambda m: f"{weights[date.fromisoformat(m.group(1))]}", s)
        s = re.sub(r"\{pct@(\d{4}-\d{2}-\d{2})@(\d{4}-\d{2}-\d{2})\}",
                   lambda m: f"{(weights[date.fromisoformat(m.group(2))] - weights[date.fromisoformat(m.group(1))]) / weights[date.fromisoformat(m.group(1))] * 100:+.1f}", s)
        return s

    notes_out = []
    for n in cb.notes:
        facts = [resolve(f) for f in n.facts]
        assert not any("{" in f for f in facts), (pid, n.doc_id, facts)
        disp, author, dtype, _ = C.SETTINGS[n.setting]
        v = None
        if n.vitals:
            bp = bps[n.date]
            v = {"weight_kg": weights[n.date], "bmi": bmis[n.date], "bp": f"{bp[0]}/{bp[1]}", "height_cm": cb.h_cm}
        notes_out.append({
            "doc_id": n.doc_id, "date": n.date.isoformat(), "setting": n.setting, "note_type": disp,
            "doc_type_loinc": C.DOC_TYPES[dtype][0], "doc_type_display": C.DOC_TYPES[dtype][1], "author_role": author,
            "encounter_id": n.encounter_id, "role": n.role, "trap": n.trap, "length": n.length,
            "vitals": v, "facts_to_express": facts, "must_not_say": C.MUST_NOT_SAY,
        })

    # ---------- annotations ----------
    anns = []

    def add(resource_id, a):
        anns.append({"patient_id": pid, "resource_id": resource_id, **a})

    for n in cb.notes:
        for a in n.anns:
            add(f"DocumentReference/{n.doc_id}", a)
    for c in conditions:
        if "_ann" in c:
            add(f"Condition/{c['id']}", c.pop("_ann"))
    for m in meds:
        if "_ann" in m:
            add(f"{m['resourceType']}/{m['id']}", m.pop("_ann"))
    add(f"Observation/{pid}-BMI-{t_end.isoformat()}", A("bmi", "NEUTRAL", bmi_value=bmis[t_end], source="structured_latest"))
    if cb.bmi_conflict_041 and len(vit_dates) >= 2:
        add(f"Observation/{pid}-BMI-{vit_dates[-2].isoformat()}", A("bmi", "NEUTRAL", bmi_value=bmis[vit_dates[-2]], source="structured_prior"))
    add(f"Patient/{pid}", A("age", "NEUTRAL", age=p["demographics"]["age"], source="structured"))

    by = rng.randint(1, 364)
    birth = date(INDEX_DATE.year - p["demographics"]["age"], INDEX_DATE.month, INDEX_DATE.day) - timedelta(days=by)
    sex = p["demographics"]["sex"]
    plan = {
        "patient_id": pid,
        "index_date": INDEX_DATE.isoformat(),
        "patient": {"id": pid, "given": rng.choice(C.FIRST_NAMES[sex]), "family": rng.choice(C.LAST_NAMES),
                    "gender": sex, "birthDate": birth.isoformat()},
        "conditions": conditions,
        "observations": obs,
        "medications": meds,
        "encounters": encounters,
        "notes": notes_out,
        "generator_notes": cb.decisions,
    }
    return plan, anns

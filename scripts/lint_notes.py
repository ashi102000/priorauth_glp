"""M1.4: lint authored notes against their plans.

Checks per patient (only patients with compiled notes unless --strict):
  coverage       every planned doc_id has text, and no extra doc_ids exist
  leakage        banned policy phrases and answer-key vocabulary are absent
  header_date    the first MM/DD/YYYY in the note equals the planned date
  vitals         vitals notes state the recorded weight, BMI and BP
  plan_numbers   every number in facts_to_express appears in the text
  weight_values  every "NN.N kg" in the text matches an Observation weight (or a planned narrative value)
  future_dates   no full date later than the note date + 60 days
"""
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from pa_bench.generation.catalog import MUST_NOT_SAY  # noqa: E402

LEAK_TERMS = ["easy_positive", "easy_negative", "missing_evidence", "benchmark", "ground truth", "ground_truth",
              "challenge_tag", "annotation", "SUPPORTS", "CONTRADICTS", "documentation_state", "synthetic"]
NUM = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?")


def norm(s: str) -> str:
    return s.replace("−", "-").replace("–", "-")


def lint_patient(pid: str) -> list[str]:
    plan = json.loads((ROOT / f"data/_generation/plans/{pid}.json").read_text())
    notes = json.loads((ROOT / f"data/notes/{pid}.json").read_text())["notes"]
    errs = []
    planned = {n["doc_id"]: n for n in plan["notes"]}
    for d in planned.keys() - notes.keys():
        errs.append(f"coverage: missing note {d}")
    for d in notes.keys() - planned.keys():
        errs.append(f"coverage: unplanned note {d}")
    obs_weights = {o["value"] for o in plan["observations"] if o["key"] == "WT"}
    narrative_weights = {float(x) for n in plan["notes"] for f in n["facts_to_express"] for x in re.findall(r"(\d{2,3}\.\d) kg", f)}
    for doc_id, text in notes.items():
        n = planned.get(doc_id)
        if not n:
            continue
        t, low = norm(text), text.lower()
        for ph in MUST_NOT_SAY:
            if ph.lower() in low:
                errs.append(f"leakage: {doc_id} contains banned phrase '{ph}'")
        for term in LEAK_TERMS:
            if (term in text) if term.isupper() else (term in low):
                errs.append(f"leakage: {doc_id} contains answer-key term '{term}'")
        m = re.search(r"(\d{2})/(\d{2})/(\d{4})", t)
        nd = date.fromisoformat(n["date"])
        if not m:
            errs.append(f"header_date: {doc_id} has no MM/DD/YYYY date")
        else:
            hd = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
            if hd != nd:
                errs.append(f"header_date: {doc_id} header {hd} != plan {nd}")
        for mm, dd, yy in re.findall(r"(\d{2})/(\d{2})/(\d{4})", t):
            if date(int(yy), int(mm), int(dd)) > nd + timedelta(days=60):
                errs.append(f"future_dates: {doc_id} mentions {mm}/{dd}/{yy}")
        v = n["vitals"]
        if v:
            for label, val in (("weight", v["weight_kg"]), ("BMI", v["bmi"]), ("BP", v["bp"])):
                if str(val) not in t:
                    errs.append(f"vitals: {doc_id} missing {label} {val}")
        for f in n["facts_to_express"]:
            for x in NUM.findall(norm(f)):
                xs = x.lstrip("+")
                if xs.lstrip("-") in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
                    continue   # small integers are phrased freely ("3 months", "two sodas")
                if xs not in t and xs.lstrip("-") not in t:
                    errs.append(f"plan_numbers: {doc_id} missing '{xs}' from fact: {f[:90]}")
        for w in re.findall(r"(\d{2,3}\.\d)\s?kg", t):
            if float(w) not in obs_weights | narrative_weights:
                errs.append(f"weight_values: {doc_id} states {w} kg, not an Observation weight")
    return errs


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    pids = [a for a in argv if a.startswith("GLP1-")]
    plans = sorted(p.stem for p in (ROOT / "data/_generation/plans").glob("GLP1-*.json"))
    targets = pids or plans
    total, checked = 0, 0
    for pid in targets:
        if not (ROOT / f"data/notes/{pid}.json").exists():
            if strict:
                print(f"{pid}: NO NOTES")
                total += 1
            continue
        checked += 1
        errs = lint_patient(pid)
        total += len(errs)
        print(f"{pid}: {'OK' if not errs else f'{len(errs)} issue(s)'}")
        for e in errs:
            print("   ", e)
    print(f"\nchecked {checked} patients, {total} issue(s)")
    print("RESULT:", "FAIL" if total else "PASS")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

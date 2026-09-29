"""M1.6 (local): verify the benchmark's FHIR client serves exactly the generated cohort.

Replaces the HAPI seed/verify step (the cohort is served from local bundles; see DECISIONS.md).
Checks per patient: resource counts through LocalBundleClient == chart plan, every note decodes to
the frozen text, Patient demographics resolve, and read() round-trips every id.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from pa_bench.fhir.client import LocalBundleClient  # noqa: E402
from pa_bench.fhir.parser import document_text  # noqa: E402


def main() -> int:
    client = LocalBundleClient()
    errors = []
    pids = client.patient_ids()
    if len(pids) != 50:
        errors.append(f"expected 50 patients, found {len(pids)}")
    for pid in pids:
        plan = json.loads((ROOT / f"data/_generation/plans/{pid}.json").read_text())
        notes = json.loads((ROOT / f"data/notes/{pid}.json").read_text())["notes"]
        ev = client.everything(pid)
        got = Counter({t: len(rs) for t, rs in ev.items()})
        want = Counter({"Patient": 1, "Encounter": len(plan["encounters"]), "Condition": len(plan["conditions"]),
                        "Observation": len(plan["observations"]), "DocumentReference": len(plan["notes"])})
        want.update(Counter(m["resourceType"] for m in plan["medications"]))
        if got != want:
            errors.append(f"{pid}: counts {dict(got)} != plan {dict(want)}")
        for d in ev.get("DocumentReference", []):
            if document_text(d) != notes[d["id"]]:
                errors.append(f"{pid}: text mismatch {d['id']}")
        for t, rs in ev.items():
            for r in rs:
                if client.read(t, r["id"]) is not r:
                    errors.append(f"{pid}: read() mismatch {t}/{r['id']}")
    print(f"patients served: {len(pids)}  resources: {sum(len(rs) for p in pids for rs in client.everything(p).values())}")
    for e in errors[:30]:
        print("ERROR", e)
    print("RESULT:", "FAIL" if errors else "PASS")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

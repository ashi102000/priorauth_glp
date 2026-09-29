"""Dev helper: compact view of note plans for note writing."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for pid in sys.argv[1:]:
    p = json.loads((ROOT / f"data/_generation/plans/{pid}.json").read_text())
    pt = p["patient"]
    print("=====", pid, pt["given"], pt["family"], pt["gender"], pt["birthDate"], "| conds:",
          [c["display"] + ("" if c["clinical_status"] == "active" else f"({c['clinical_status']})") for c in p["conditions"]],
          "| meds:", [m["text"] + ("" if m["status"] == "active" else f" [{m['resourceType']} {m['status']}]") for m in p["medications"] if not m.get("requested_drug")])
    for n in p["notes"]:
        v = n["vitals"]
        vs = f" WT {v['weight_kg']} BMI {v['bmi']} BP {v['bp']}" if v else ""
        print(f"{n['doc_id']} {n['date']} [{n['note_type']}; {n['length']}]{vs}")
        for f in n["facts_to_express"]:
            if not f.startswith("Unrelated to weight"):
                print("   -", f)

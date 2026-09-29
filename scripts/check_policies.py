"""P2.2: validate normalized policies against schemas/policy.schema.json and check every source_quote
segment (split on ' ... ' and ' / ') appears verbatim (whitespace-normalized) in the saved local source copies."""
import json
import re
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def main() -> int:
    schema = json.loads((ROOT / "schemas/policy.schema.json").read_text())
    errors, n_seg = [], 0
    policies = sorted(p for p in (ROOT / "policies").glob("*.json") if not p.name.startswith("_"))
    for pp in policies:
        pol = json.loads(pp.read_text())
        try:
            jsonschema.validate(pol, schema)
        except jsonschema.ValidationError as e:
            errors.append(f"{pp.name}: schema: {e.message}")
        if pol["policy_id"] + ".json" != pp.name:
            errors.append(f"{pp.name}: filename != policy_id")
        corpus = norm(" ".join((ROOT / c).read_text() for c in pol["source"]["local_copies"]))
        ids = [c["criterion_id"] for c in pol["criteria"]]
        if len(ids) != len(set(ids)):
            errors.append(f"{pp.name}: duplicate criterion ids")
        logic_ids = set(re.findall(r'"([a-z0-9_]+)"', json.dumps(pol["decision_logic"]))) - {"all_of", "any_of"}
        if logic_ids != set(ids):
            errors.append(f"{pp.name}: decision_logic ids {sorted(logic_ids)} != criteria {sorted(ids)}")
        for c in pol["criteria"]:
            for seg in re.split(r"\s\.\.\.\s|\s/\s", c["source_quote"]):
                seg = seg.strip(" .:")
                if len(seg) < 12:
                    continue
                n_seg += 1
                if norm(seg) not in corpus:
                    errors.append(f"{pp.name}:{c['criterion_id']}: quote segment not found in sources: '{seg[:90]}'")
        print(f"{pol['policy_id']:<36} criteria={len(ids)} logic={pol['decision_logic']} status={pol['human_verification']['status']}")
    print(f"\nquote segments checked: {n_seg}")
    for e in errors:
        print("ERROR", e)
    print("RESULT:", "FAIL" if errors else "PASS")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

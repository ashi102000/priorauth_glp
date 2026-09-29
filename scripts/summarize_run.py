"""Quick sanity summary of a run directory (full evaluation lives in Phase 8)."""
import json
import statistics as st
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] if xs else None


def main(run_ids):
    truth = {r["evaluation_id"]: r["ground_truth"] for r in json.loads((ROOT / "ground_truth/pa_truth.json").read_text())["evaluations"]}
    for rid in run_ids:
        rows = [json.loads(l) for l in (ROOT / "results/runs" / rid / "results.jsonl").read_text().splitlines()]
        latest = {r["evaluation_id"]: r for r in rows}          # last attempt wins
        ok = [r for r in latest.values() if not r.get("error")]
        corr = sum(r["pa_state"] == truth[r["evaluation_id"]]["pa_state"] for r in ok)
        ccorr = sum(r["criteria"][k]["status"] == v["status"] for r in ok for k, v in truth[r["evaluation_id"]]["criteria"].items())
        ctot = sum(len(truth[r["evaluation_id"]]["criteria"]) for r in ok)
        lat = [r["latency_ms"]["total"] for r in ok]
        dec = [r["latency_ms"].get("decision_total", r["latency_ms"]["total"]) for r in ok]
        calls = Counter(c["provider"] for r in ok for c in r["calls"])
        esc = sum(bool(r.get("escalated_criteria")) for r in ok)
        print(f"{rid}: {len(latest)} evals, {len(latest) - len(ok)} errors | PA acc {corr}/{len(ok)} = {corr / max(1, len(ok)):.3f} | "
              f"criterion acc {ccorr}/{ctot} = {ccorr / max(1, ctot):.3f}")
        print(f"   cost ${sum(r['cost_usd'] for r in ok):.4f} | calls {dict(calls)} | cases escalated {esc} | "
              f"latency ms total p50 {pct(lat, .5):.0f} p95 {pct(lat, .95):.0f} | decision p50 {pct(dec, .5):.0f} p95 {pct(dec, .95):.0f}")
        wrong = [(r["evaluation_id"], truth[r["evaluation_id"]]["pa_state"], r["pa_state"]) for r in ok if r["pa_state"] != truth[r["evaluation_id"]]["pa_state"]]
        for w in wrong:
            print("   ✗", *w)


if __name__ == "__main__":
    main(sys.argv[1:])

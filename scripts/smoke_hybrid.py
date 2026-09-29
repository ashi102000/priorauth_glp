"""Phase 6 smoke test: hybrid pipeline on the same patients as the GPT smoke test.
Usage: python scripts/smoke_hybrid.py [--threshold 0.9] [GLP1-...]"""
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")
from pa_bench.benchmark.trace import TraceWriter, trace_row  # noqa: E402
from pa_bench.config import request_date  # noqa: E402
from pa_bench.evaluation.cost import record_cost  # noqa: E402
from pa_bench.fhir.client import LocalBundleClient  # noqa: E402
from pa_bench.models.jev_provider import JevProvider  # noqa: E402
from pa_bench.models.openai_provider import OpenAIProvider  # noqa: E402
from pa_bench.pipelines import hybrid  # noqa: E402
from pa_bench.policies.loader import load_all  # noqa: E402
from pa_bench.retrieval.profile import build_profile  # noqa: E402

DEFAULT = ["GLP1-001", "GLP1-016", "GLP1-029", "GLP1-038", "GLP1-043"]


def main(argv):
    thr = float(argv[argv.index("--threshold") + 1]) if "--threshold" in argv else 0.90
    pids = [a for a in argv if a.startswith("GLP1-")] or DEFAULT
    client, policies, jev, llm = LocalBundleClient(), load_all(), JevProvider(), OpenAIProvider()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    out = ROOT / f"results/smoke/hybrid_{run_id}"
    tw = TraceWriter(out / "traces.jsonl")
    truth = {r["evaluation_id"]: r["ground_truth"] for r in json.loads((ROOT / "ground_truth/pa_truth.json").read_text())["evaluations"]}
    lines = [f"# Hybrid smoke test {run_id} (threshold {thr})", "",
             "| evaluation | truth | predicted | ok | criteria ok | escalated | jev q | gpt calls | latency ms (decision/total) | cost $ |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    tot = 0.0
    for pid in pids:
        for pol in policies:
            t0 = time.perf_counter()
            prof = build_profile(client, pid, pol, request_date())
            res = hybrid.run(prof, pol, jev, llm, threshold=thr, retrieval_latency_ms=(time.perf_counter() - t0) * 1000)
            eid = f"{pid}__{pol['policy_id']}"
            res.update({"run_id": run_id, "evaluation_id": eid})
            for call in res["calls"]:
                tw.write(trace_row(run_id=run_id, evaluation_id=eid, pipeline="hybrid", call=call, result=res["pa_state"]))
            with (out / "results.jsonl").open("a") as f:
                f.write(json.dumps(res, ensure_ascii=False, default=str) + "\n")
            g = truth[eid]
            wrong = [f"{k}:{res['criteria'][k]['status']}≠{v['status']}" for k, v in g["criteria"].items() if res["criteria"][k]["status"] != v["status"]]
            cost = sum(record_cost(c) or 0 for c in res["calls"])
            tot += cost
            n_gpt = sum(c["provider"] == "openai" for c in res["calls"])
            lines.append(f"| {eid} | {g['pa_state']} | {res['pa_state']} | {'✅' if g['pa_state'] == res['pa_state'] else '❌'} | "
                         f"{len(g['criteria']) - len(wrong)}/{len(g['criteria'])} | {','.join(res['escalated_criteria']) or '—'} | "
                         f"{res['jev_questions']} | {n_gpt} | {res['latency_ms']['decision_total']}/{res['latency_ms']['total']} | {cost:.4f} |")
            print(lines[-1], flush=True)
            if wrong or res["notes"]:
                print("   wrong:", wrong, "notes:", res["notes"])
    lines += ["", f"Total cost: ${tot:.4f}"]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print(f"\nTotal cost ${tot:.4f} — {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])

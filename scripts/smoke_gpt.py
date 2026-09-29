"""Phase 4 smoke test: GPT baseline on a handful of patients x all 3 policies.

Usage:
  python scripts/smoke_gpt.py --dry-run                 # build prompts, count tokens, estimate cost; no API calls
  python scripts/smoke_gpt.py [GLP1-001 GLP1-016 ...]    # live run (default 5 diverse patients)
Outputs: results/smoke/gpt_<run_id>/{results.jsonl, traces.jsonl, summary.md}
"""
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from pa_bench.benchmark.trace import TraceWriter, trace_row  # noqa: E402
from pa_bench.config import request_date  # noqa: E402
from pa_bench.evaluation.cost import cost_usd, record_cost  # noqa: E402
from pa_bench.fhir.client import LocalBundleClient  # noqa: E402
from pa_bench.pipelines import gpt  # noqa: E402
from pa_bench.policies.loader import load_all  # noqa: E402
from pa_bench.retrieval.profile import build_profile, cached_profile, count_tokens  # noqa: E402

DEFAULT = ["GLP1-001", "GLP1-016", "GLP1-029", "GLP1-038", "GLP1-043"]


def main(argv):
    dry = "--dry-run" in argv
    pids = [a for a in argv if a.startswith("GLP1-")] or DEFAULT
    client, policies = LocalBundleClient(), load_all()
    if dry:
        tot = 0
        for pid in pids:
            for pol in policies:
                prof = cached_profile(client, pid, pol, request_date())
                n = count_tokens(gpt.SYSTEM) + count_tokens(gpt.build_prompt(prof, pol))
                tot += n
                print(f"{pid} {pol['policy_id'][:10]:<10} prompt≈{n} tok")
        est_out = 2500 * len(pids) * len(policies)
        import os
        m = os.environ.get("OPENAI_MODEL", "gpt-6-sol")
        print(f"\ncalls={len(pids) * len(policies)} input≈{tot} tok; est. cost (assuming ~2.5K output/reasoning tok per call): "
              f"${cost_usd(m, tot, 0, est_out):.3f}")
        return 0

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from pa_bench.models.openai_provider import OpenAIProvider
    llm = OpenAIProvider()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    out = ROOT / f"results/smoke/gpt_{run_id}"
    tw = TraceWriter(out / "traces.jsonl")
    truth = {r["evaluation_id"]: r["ground_truth"] for r in json.loads((ROOT / "ground_truth/pa_truth.json").read_text())["evaluations"]}
    lines = [f"# GPT smoke test {run_id}", "", f"model `{llm.model}`, reasoning effort `{llm.reasoning_effort}`", "",
             "| evaluation | truth | predicted | ok | criteria correct | in tok | out tok (reasoning) | latency ms | cost $ |",
             "|---|---|---|---|---|---|---|---|---|"]
    tot_cost = 0.0
    for pid in pids:
        for pol in policies:
            t0 = time.perf_counter()
            prof = build_profile(client, pid, pol, request_date())
            retr_ms = (time.perf_counter() - t0) * 1000
            assert prof == json.loads(json.dumps(cached_profile(client, pid, pol, request_date()))), "profile differs from cache"
            res = gpt.run(prof, pol, llm, retrieval_latency_ms=retr_ms)
            eid = f"{pid}__{pol['policy_id']}"
            res.update({"run_id": run_id, "evaluation_id": eid})
            call = res["calls"][0]
            for cid, c in res["criteria"].items():
                pass
            tw.write(trace_row(run_id=run_id, evaluation_id=eid, pipeline="gpt", call=call, result=res["pa_state"],
                               evidence_ids=sorted({i for c in res["criteria"].values() for i in c["evidence_ids"]})))
            with (out / "results.jsonl").open("a") as f:
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
            g = truth[eid]
            crit_ok = sum(res["criteria"][k]["status"] == v["status"] for k, v in g["criteria"].items())
            c_usd = record_cost(call) or 0.0
            tot_cost += c_usd
            lines.append(f"| {eid} | {g['pa_state']} | {res['pa_state']} | {'✅' if g['pa_state'] == res['pa_state'] else '❌'} | "
                         f"{crit_ok}/{len(g['criteria'])} | {call['input_tokens']} | {call['output_tokens']} ({call['reasoning_tokens']}) | "
                         f"{call['latency_ms']} | {c_usd:.4f} |")
            print(lines[-1], flush=True)
            if res["error"] or res["notes"]:
                print("   notes:", res["error"], res["notes"])
    lines += ["", f"Total cost: ${tot_cost:.4f}"]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print(f"\nTotal cost ${tot_cost:.4f} — outputs in {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

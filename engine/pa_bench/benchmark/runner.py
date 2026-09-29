"""Benchmark runner: checkpointed, resumable, concurrent; one results.jsonl row per evaluation."""
from __future__ import annotations

import json
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ..config import request_date
from ..evaluation.cost import record_cost
from ..fhir.client import LocalBundleClient
from ..pipelines import gpt, hybrid
from ..retrieval.profile import build_profile, cached_profile
from .trace import TraceWriter, trace_row


def completed_ids(run_dir: Path) -> set[str]:
    p = run_dir / "results.jsonl"
    if not p.exists():
        return set()
    done = set()
    for line in p.read_text().splitlines():
        r = json.loads(line)
        if not r.get("error"):
            done.add(r["evaluation_id"])
    return done


class Runner:
    def __init__(self, run_dir: Path, pipeline: str, llm, jev=None, *, threshold: float | None = None,
                 narrative_mode: str | None = None, concurrency: int = 4):
        self.run_dir, self.pipeline, self.llm, self.jev = run_dir, pipeline, llm, jev
        self.threshold, self.narrative_mode, self.concurrency = threshold, narrative_mode, concurrency
        self.client = LocalBundleClient()
        self.tw = TraceWriter(run_dir / "traces.jsonl")
        self._lock = threading.Lock()

    def _one(self, pid: str, policy: dict, run_id: str) -> dict:
        eid = f"{pid}__{policy['policy_id']}"
        t0 = time.perf_counter()
        prof = build_profile(self.client, pid, policy, request_date())
        retr_ms = (time.perf_counter() - t0) * 1000
        if json.loads(json.dumps(prof)) != cached_profile(self.client, pid, policy, request_date()):
            raise RuntimeError(f"{eid}: evidence profile differs from the shared cache")
        try:
            if self.pipeline == "gpt":
                res = gpt.run(prof, policy, self.llm, retrieval_latency_ms=retr_ms)
            else:
                res = hybrid.run(prof, policy, self.jev, self.llm, threshold=self.threshold,
                                 narrative_mode=self.narrative_mode, retrieval_latency_ms=retr_ms)
        except Exception as e:  # noqa: BLE001
            res = {"pipeline": self.pipeline, "patient_id": pid, "policy_id": policy["policy_id"], "calls": [],
                   "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-2000:]}
        res.update({"run_id": run_id, "evaluation_id": eid, "profile_tokens": prof["meta"]["tokens"]})
        if res.get("calls") and any(c.get("error") and c.get("parsed") is None for c in res["calls"]):
            res["error"] = res.get("error") or "; ".join(c["error"] for c in res["calls"] if c.get("error") and c.get("parsed") is None)
        res["cost_usd"] = round(sum(record_cost(c) or 0.0 for c in res.get("calls", [])), 8)
        with self._lock:
            for call in res.get("calls", []):
                crit = None
                if call["stage"] == "gpt_escalation":
                    crit = ",".join(res.get("escalated_criteria", []))
                self.tw.write(trace_row(run_id=run_id, evaluation_id=eid, pipeline=self.pipeline, call=call,
                                        criterion_id=crit, result=res.get("pa_state")))
            with (self.run_dir / "results.jsonl").open("a") as f:
                f.write(json.dumps(res, ensure_ascii=False, default=str) + "\n")
        return res

    def run(self, jobs: list[tuple[str, dict]], run_id: str, force: bool = False, progress=print) -> dict:
        done = set() if force else completed_ids(self.run_dir)
        todo = [(pid, pol) for pid, pol in jobs if f"{pid}__{pol['policy_id']}" not in done]
        progress(f"[{run_id}] {len(jobs)} evaluations; {len(done)} already complete; running {len(todo)}")
        stats = {"ok": 0, "error": 0, "cost": 0.0}
        with ThreadPoolExecutor(max_workers=self.concurrency) as ex:
            futs = {ex.submit(self._one, pid, pol, run_id): (pid, pol) for pid, pol in todo}
            for n, fut in enumerate(as_completed(futs), 1):
                r = fut.result()
                stats["error" if r.get("error") else "ok"] += 1
                stats["cost"] += r.get("cost_usd", 0.0)
                if n % 10 == 0 or n == len(todo) or r.get("error"):
                    progress(f"  {len(done) + n}/{len(jobs)}  last={r['evaluation_id']} state={r.get('pa_state')} "
                             f"err={r.get('error') or '-'}  run cost so far ${stats['cost']:.4f}")
        return stats

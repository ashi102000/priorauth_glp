"""P3: build + cache evidence profiles for all 150 patient x policy pairs and evaluate retrieval.

Outputs:
  data/cache/profiles/<config_hash>/<pid>__<policy>.json   (model-visible; shared by all arms)
  results/retrieval/retrieval_results.csv                 (one row per patient x policy x criterion)
  reports/retrieval_eval.md                               (+ K sensitivity, reported not tuned)
Usage: python scripts/build_profiles.py [--refresh] [--sensitivity]
"""
import csv
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from pa_bench.config import request_date, retrieval_config  # noqa: E402
from pa_bench.evaluation.retrieval_metrics import COMORBIDITY_CONCEPTS, criterion_metrics, index_annotations  # noqa: E402
from pa_bench.fhir.client import LocalBundleClient  # noqa: E402
from pa_bench.policies.loader import load_all  # noqa: E402
from pa_bench.retrieval.profile import build_profile, cached_profile, config_hash  # noqa: E402


def evaluate(profiles, policies, ann_idx, truth, spec):
    rows = []
    pol_by = {p["policy_id"]: p for p in policies}
    for prof in profiles:
        pid, pol = prof["patient_id"], pol_by[prof["policy_id"]]
        concepts = {c["criterion_id"]: c["evidence_concepts"] for c in pol["criteria"]}
        for cid, ev in prof["evidence"].items():
            docs = {e["resource_id"] for e in ev}
            status = truth.get((pid, pol["policy_id"], cid))
            m = criterion_metrics(pid, COMORBIDITY_CONCEPTS if cid == "comorbidity" else concepts[cid], docs, ann_idx, status)
            rows.append({"patient_id": pid, "policy_id": pol["policy_id"], "criterion_id": cid,
                         "difficulty": spec[pid]["benchmark_design"]["class"], "truth_status": status or "", **m,
                         "retrieved_ids": ";".join(sorted(docs)), "missed": ";".join(m["missed"])})
    return rows


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(st.mean(xs), 3) if xs else None


def summarize(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[r[key]].append(r)
    out = []
    for k, rs in sorted(g.items()):
        crit = [r["critical_hit"] for r in rs if r["critical_hit"] is not None]
        out.append((k, len(rs), mean(r["recall"] for r in rs), mean(r["precision"] for r in rs),
                    mean(r["recall_supports"] for r in rs), mean(r["recall_contradicts"] for r in rs),
                    mean(r["recall_ambiguous"] for r in rs), round(st.mean(r["hard_negatives_retrieved"] for r in rs), 2),
                    f"{sum(crit)}/{len(crit)}" if crit else "—"))
    return out


def table(title, rows):
    L = [f"### {title}", "", "| group | n | recall | precision | recall SUPPORTS | recall CONTRADICTS | recall AMBIGUOUS | hard-neg / query | critical hits |",
         "|---|---|---|---|---|---|---|---|---|"]
    L += ["| " + " | ".join("—" if v is None else str(v) for v in r) + " |" for r in rows]
    return L + [""]


def main(argv):
    refresh = "--refresh" in argv
    client = LocalBundleClient()
    policies = load_all()
    spec = {p["patient_id"]: p for p in json.loads((ROOT / "data/cohort/patients.json").read_text())["patients"]}
    ann_idx = index_annotations(json.loads((ROOT / "ground_truth/evidence_map.json").read_text())["annotations"])
    truth = {(r["patient_id"], r["policy_id"], r["criterion_id"]): r["status"]
             for r in json.loads((ROOT / "ground_truth/criterion_truth.json").read_text())["rows"]}
    cfg = retrieval_config()
    profiles = [cached_profile(client, pid, pol, request_date(), cfg, refresh=refresh)
                for pid in client.patient_ids() for pol in policies]
    rows = evaluate(profiles, policies, ann_idx, truth, spec)

    out = ROOT / "results/retrieval"
    out.mkdir(parents=True, exist_ok=True)
    fields = ["patient_id", "policy_id", "criterion_id", "difficulty", "truth_status", "n_relevant", "n_retrieved", "n_hit",
              "recall", "precision", "recall_supports", "recall_contradicts", "recall_ambiguous",
              "hard_negatives_retrieved", "critical_hit", "retrieved_ids", "missed"]
    with open(out / "retrieval_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    tok = [p["meta"]["tokens"] for p in profiles]
    red = [1 - t["profile_total"] / t["raw_chart"]["total"] for t in tok]
    L = ["# Retrieval evaluation (Phase 3)", "",
         f"Config `{cfg['version']}` (hash `{config_hash(cfg)}`): top_k={cfg['top_k']}, min_relative_score={cfg['min_relative_score']}, "
         f"temporal extras={cfg['temporal_extras']}, chunk ≤{cfg['chunking']['max_words']} words, BM25 k1={cfg['bm25']['k1']} b={cfg['bm25']['b']}. "
         "Defaults fixed a priori; not tuned on these annotations.", "",
         f"Profiles: {len(profiles)} (50 patients × {len(policies)} policies); criterion queries evaluated: {len(rows)}.", "",
         "Document-level metrics vs. hidden evidence annotations. Structured resources are always supplied in full and not scored.", ""]
    L += table("By criterion", summarize(rows, "criterion_id"))
    L += table("By difficulty class", summarize(rows, "difficulty"))
    L += table("By policy", summarize(rows, "policy_id"))
    L += ["### Context size (tiktoken cl100k_base, per patient × policy profile)", "",
          "| measure | min | median | max |", "|---|---|---|---|",
          f"| raw candidate chart (structured JSON + decoded notes) | {min(t['raw_chart']['total'] for t in tok)} | {st.median(t['raw_chart']['total'] for t in tok)} | {max(t['raw_chart']['total'] for t in tok)} |",
          f"| retrieved note evidence (unique chunks) | {min(t['retrieved_evidence'] for t in tok)} | {st.median(t['retrieved_evidence'] for t in tok)} | {max(t['retrieved_evidence'] for t in tok)} |",
          f"| structured features | {min(t['structured_features'] for t in tok)} | {st.median(t['structured_features'] for t in tok)} | {max(t['structured_features'] for t in tok)} |",
          f"| full evidence profile | {min(t['profile_total'] for t in tok)} | {st.median(t['profile_total'] for t in tok)} | {max(t['profile_total'] for t in tok)} |",
          f"| context reduction (1 − profile / raw chart) | {min(red):.1%} | {st.median(red):.1%} | {max(red):.1%} |", ""]
    misses = [r for r in rows if r["critical_hit"] is False]
    L += ["### Critical misses (truth FAIL/CONFLICT but no contradicting/ambiguous evidence retrieved)", ""]
    L += [f"- {r['patient_id']} · {r['policy_id']} · {r['criterion_id']} — missed {r['missed']}" for r in misses] or ["- none"]
    low = sorted((r for r in rows if r["recall"] is not None and r["recall"] < 0.5), key=lambda r: r["recall"])
    L += ["", f"### Low-recall queries (recall < 0.5): {len(low)}", ""]
    L += [f"- {r['patient_id']} · {r['policy_id'].split('_')[0]} · {r['criterion_id']}: recall {r['recall']:.2f} ({r['n_hit']}/{r['n_relevant']}), missed {r['missed']}" for r in low[:25]]

    if "--sensitivity" in argv:
        L += ["", "### Sensitivity to top_k (reported only — the benchmark uses the fixed default)", "",
              "| top_k | recall | precision | recall CONTRADICTS | critical hits | median profile tokens |", "|---|---|---|---|---|---|"]
        for k in (3, 5, 8, 12):
            cfg_k = {**cfg, "top_k": k}
            profs_k = [build_profile(client, pid, pol, request_date(), cfg_k) for pid in client.patient_ids() for pol in policies]
            rk = evaluate(profs_k, policies, ann_idx, truth, spec)
            crit = [r["critical_hit"] for r in rk if r["critical_hit"] is not None]
            L.append(f"| {k} | {mean(r['recall'] for r in rk)} | {mean(r['precision'] for r in rk)} | {mean(r['recall_contradicts'] for r in rk)} | "
                     f"{sum(crit)}/{len(crit)} | {st.median(p['meta']['tokens']['profile_total'] for p in profs_k)} |")
    (ROOT / "reports/retrieval_eval.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

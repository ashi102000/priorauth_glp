"""Quality, calibration, latency and statistical-comparison metrics (evaluation-only; pure functions)."""
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict

PA_CLASSES = ("READY", "NOT_READY", "REVIEW_REQUIRED")
STATUS_CLASSES = ("PASS", "FAIL", "INSUFFICIENT", "CONFLICT")


# ------------------------------------------------------------------------------------------ classification
def confusion(truth: list[str], pred: list[str], classes) -> dict[str, dict[str, int]]:
    m = {t: {p: 0 for p in classes} for t in classes}
    for t, p in zip(truth, pred):
        m[t][p] += 1
    return m


def prf(truth: list[str], pred: list[str], classes) -> dict:
    per = {}
    for c in classes:
        tp = sum(t == c and p == c for t, p in zip(truth, pred))
        fp = sum(t != c and p == c for t, p in zip(truth, pred))
        fn = sum(t == c and p != c for t, p in zip(truth, pred))
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / (tp + fn) if tp + fn else None
        f1 = (2 * prec * rec / (prec + rec)) if prec and rec else (0.0 if (tp + fp and tp + fn) else None)
        per[c] = {"precision": prec, "recall": rec, "f1": f1, "support": tp + fn}
    f1s = [v["f1"] for v in per.values() if v["support"] and v["f1"] is not None]
    acc = sum(t == p for t, p in zip(truth, pred)) / len(truth) if truth else None
    return {"accuracy": acc, "macro_f1": sum(f1s) / len(f1s) if f1s else None, "per_class": per,
            "confusion": confusion(truth, pred, classes), "n": len(truth)}


def binary(truth: list[bool], pred: list[bool]) -> dict:
    tp = sum(t and p for t, p in zip(truth, pred))
    fp = sum((not t) and p for t, p in zip(truth, pred))
    fn = sum(t and not p for t, p in zip(truth, pred))
    tn = sum((not t) and (not p) for t, p in zip(truth, pred))
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    return {"accuracy": (tp + tn) / len(truth), "precision": prec, "recall": rec,
            "f1": (2 * prec * rec / (prec + rec)) if prec and rec else 0.0,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn, "false_auto_submissions": fp}


# ------------------------------------------------------------------------------------------ calibration
def calibration(conf: list[float], correct: list[bool], n_bins: int = 10) -> dict:
    """Confidence calibration of 'the chosen answer is correct'. Bins report n; ECE is n-weighted."""
    if not conf:
        return {"n": 0, "brier": None, "ece": None, "bins": []}
    brier = sum((c - (1.0 if y else 0.0)) ** 2 for c, y in zip(conf, correct)) / len(conf)
    bins = []
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        idx = [i for i, c in enumerate(conf) if (lo <= c < hi) or (b == n_bins - 1 and c == 1.0)]
        if not idx:
            bins.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": 0, "mean_confidence": None, "empirical_accuracy": None})
            continue
        bins.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": len(idx), "mean_confidence": sum(conf[i] for i in idx) / len(idx),
                     "empirical_accuracy": sum(correct[i] for i in idx) / len(idx)})
    ece = sum(b["n"] * abs(b["mean_confidence"] - b["empirical_accuracy"]) for b in bins if b["n"]) / len(conf)
    return {"n": len(conf), "brier": brier, "ece": ece, "accuracy": sum(correct) / len(correct),
            "mean_confidence": sum(conf) / len(conf), "bins": bins}


# ------------------------------------------------------------------------------------------ latency
def percentiles(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0, "mean": None, "median": None, "p50": None, "p90": None, "p95": None, "max": None}
    s = sorted(xs)

    def q(p):   # linear interpolation (numpy 'linear')
        k = (len(s) - 1) * p
        f, c = math.floor(k), math.ceil(k)
        return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)
    return {"n": len(s), "mean": sum(s) / len(s), "median": q(.5), "p50": q(.5), "p90": q(.9), "p95": q(.95), "max": s[-1]}


# ------------------------------------------------------------------------------------------ statistics
def cluster_bootstrap_ci(rows: list[dict], stat, cluster_key: str = "patient_id", reps: int = 2000,
                         seed: int = 20260929, alpha: float = 0.05) -> tuple[float, float]:
    """Percentile CI resampling patients (evaluations of the same patient are correlated)."""
    groups = defaultdict(list)
    for r in rows:
        groups[r[cluster_key]].append(r)
    keys = sorted(groups)
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        sample = [r for k in (rng.choice(keys) for _ in keys) for r in groups[k]]
        v = stat(sample)
        if v is not None:
            vals.append(v)
    vals.sort()
    return vals[int(alpha / 2 * len(vals))], vals[min(len(vals) - 1, int((1 - alpha / 2) * len(vals)))]


def mcnemar_exact(a_correct: list[bool], b_correct: list[bool]) -> dict:
    """Exact two-sided McNemar test on paired correctness."""
    b = sum(x and not y for x, y in zip(a_correct, b_correct))     # A right, B wrong
    c = sum(y and not x for x, y in zip(a_correct, b_correct))     # B right, A wrong
    n = b + c
    if n == 0:
        return {"a_only_correct": b, "b_only_correct": c, "p_value": 1.0}
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return {"a_only_correct": b, "b_only_correct": c, "p_value": min(1.0, 2 * p)}


def accuracy_by(rows: list[dict], key: str, truth_key: str, pred_key: str) -> dict:
    g = defaultdict(list)
    for r in rows:
        ks = r[key] if isinstance(r[key], list) else [r[key]]
        for k in ks:
            g[k].append(r[truth_key] == r[pred_key])
    return {k: {"n": len(v), "accuracy": sum(v) / len(v)} for k, v in sorted(g.items())}


def status_counts(xs) -> dict:
    return dict(Counter(xs))

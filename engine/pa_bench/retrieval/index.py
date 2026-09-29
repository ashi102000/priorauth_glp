"""Deterministic BM25 index over one patient's note chunks (no external services)."""
from __future__ import annotations

import math
import re
from collections import Counter

from .chunker import Chunk

_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)?")
_STOP = frozenset("a an and the of to in on for with at by is was were be been are as or it this that from per x".split())


def _stem(t: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in _STOP]


class BM25Index:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(c.text)) for c in chunks]
        self.lens = [sum(d.values()) for d in self.docs]
        self.avgdl = (sum(self.lens) / len(self.lens)) if self.lens else 0.0
        df = Counter(t for d in self.docs for t in d)
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query_terms: list[str]) -> list[float]:
        q = Counter(t for term in query_terms for t in tokenize(term))
        scores = []
        for d, dl in zip(self.docs, self.lens):
            s = 0.0
            for t, qf in q.items():
                if t in d:
                    tf = d[t]
                    s += self.idf.get(t, 0.0) * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
            scores.append(round(s, 6))
        return scores

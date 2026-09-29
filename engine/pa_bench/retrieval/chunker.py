"""Split clinical notes into paragraph-level chunks with provenance."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from ..fhir.parser import document_date, document_text


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    resource_id: str
    resource_type: str
    date: str
    note_type: str
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def _split_long(par: str, max_words: int) -> list[str]:
    if len(par.split()) <= max_words:
        return [par]
    out, cur = [], []
    for sent in re.split(r"(?<=[.;])\s+", par):
        if cur and len(" ".join(cur + [sent]).split()) > max_words:
            out.append(" ".join(cur))
            cur = []
        cur.append(sent)
    if cur:
        out.append(" ".join(cur))
    return out


def chunk_document(doc: dict, max_words: int = 120, min_words: int = 25) -> list[Chunk]:
    text = document_text(doc)
    note_type = doc.get("type", {}).get("text") or "Note"
    day = document_date(doc).isoformat()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for par in paragraphs:
        pieces.extend(_split_long(par, max_words))
    merged: list[str] = []
    for piece in pieces:   # merge short fragments (headers, one-liners) forward/backward to keep context
        if merged and (len(merged[-1].split()) < min_words or len(piece.split()) < min_words) \
                and len((merged[-1] + " " + piece).split()) <= max_words:
            merged[-1] = merged[-1] + "\n" + piece
        else:
            merged.append(piece)
    rid = f"DocumentReference/{doc['id']}"
    return [Chunk(f"{rid}#c{i}", rid, "DocumentReference", day, note_type, t) for i, t in enumerate(merged)]

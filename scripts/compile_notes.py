"""Compile authored note sources (data/notes/src/*.txt) into frozen JSON (data/notes/GLP1-xxx.json).

Source format: blocks starting with a line '=== <doc_id>' followed by the note text.
The compiled JSON is model-visible content only: {patient_id, notes: {doc_id: text}}.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/notes/src"
OUT = ROOT / "data/notes"


def parse(path: Path) -> dict[str, str]:
    notes, cur, buf = {}, None, []
    for line in path.read_text().splitlines():
        m = re.match(r"^=== (GLP1-\d{3}-[A-Z]+-\d{3})\s*$", line)
        if m:
            if cur:
                notes[cur] = "\n".join(buf).strip() + "\n"
            cur, buf = m.group(1), []
            if cur in notes:
                raise ValueError(f"duplicate doc_id {cur} in {path.name}")
        else:
            buf.append(line)
    if cur:
        notes[cur] = "\n".join(buf).strip() + "\n"
    return notes


def main(pids: list[str]) -> int:
    files = sorted(SRC.glob("GLP1-*.txt")) if not pids else [SRC / f"{p}.txt" for p in pids]
    for f in files:
        pid = f.stem
        notes = parse(f)
        (OUT / f"{pid}.json").write_text(json.dumps({"patient_id": pid, "notes": notes}, indent=2, ensure_ascii=False) + "\n")
        print(f"{pid}: {len(notes)} notes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

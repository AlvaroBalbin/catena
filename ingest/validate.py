"""
Independent validation of the ingested corpus.

Re-checks the schema invariants against the written .jsonl files (not trusting the
ingest run), so `python ingest/validate.py` is a standalone integrity gate:

  1. every node has a unique id, non-empty text, and a source with a license
  2. segments rejoin to text exactly (lossless)
  3. the canonical citation parses back to the node's structural position
  4. per-part question coverage has no gaps (completeness)
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SUMMA = os.path.join(ROOT, "data", "summa")

CIT = re.compile(r"^ST (I|I-II|II-II|III|Suppl\.), q\.(\d+), a\.(\d+)$")
ID = re.compile(r"^summa\.st\.(i|i-ii|ii-ii|iii|suppl)\.q(\d+)\.a(\d+)$")


def fail(msg: str) -> None:
    print("FAIL:", msg)
    sys.exit(1)


def main() -> None:
    files = sorted(glob.glob(os.path.join(SUMMA, "summa-*.jsonl")))
    if not files:
        fail("no corpus files found; run ingest first")

    ids: set[str] = set()
    total = 0
    # part -> set of question numbers seen
    coverage: dict[str, set[int]] = {}

    for path in files:
        for ln, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.strip()
            if not line:
                continue
            node = json.loads(line)
            total += 1
            nid = node["id"]

            if nid in ids:
                fail(f"duplicate id {nid}")
            ids.add(nid)

            if not node.get("text", "").strip():
                fail(f"empty text: {nid}")

            src = node.get("source") or {}
            if not src.get("license"):
                fail(f"missing license: {nid}")

            rejoin = "\n\n".join(s["text"] for s in node["segments"])
            if rejoin != node["text"]:
                fail(f"lossless invariant broken: {nid}")

            cm = CIT.match(node["citation"])
            if not cm:
                fail(f"unparseable citation {node['citation']!r} on {nid}")
            im = ID.match(nid)
            if not im:
                fail(f"unparseable id {nid}")
            if (im.group(2), im.group(3)) != (cm.group(2), cm.group(3)):
                fail(f"id/citation mismatch: {nid} vs {node['citation']}")

            part = im.group(1)
            coverage.setdefault(part, set()).add(int(im.group(2)))

    # completeness: no gaps in question numbering within each ingested part
    expected = {"i": 119, "i-ii": 114, "ii-ii": 189, "iii": 90, "suppl": 99}
    for part, qs in coverage.items():
        want = set(range(1, expected[part] + 1))
        gaps = want - qs
        if gaps:
            fail(f"part {part}: missing questions {sorted(gaps)[:15]}")

    print(f"OK: {total} nodes, {len(ids)} unique ids")
    print("parts covered:", {p: len(q) for p, q in sorted(coverage.items())})
    print("lossless, addressable, and complete for the ingested parts.")


if __name__ == "__main__":
    main()

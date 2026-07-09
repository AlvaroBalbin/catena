"""
Walk the citation graph - the golden chain made navigable.

  python demo/refs.py "John 1:14"      every Summa article that leans on this verse
  python demo/refs.py "Romans 5"       every article citing anything in this chapter
  python demo/refs.py --article "ST I, q.2, a.3"   the verses an article rests on
  python demo/refs.py --top            the Scripture the Summa leans on most

Reads data/graph/ (build it with: python ingest/build_graph.py).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ingest"))
from scripture import normalize_ref  # noqa: E402

GRAPH = os.path.join(ROOT, "data", "graph")


def _load(name: str):
    path = os.path.join(GRAPH, name)
    if not os.path.exists(path):
        raise SystemExit("graph not built; run `python ingest/build_graph.py` first")
    return json.load(open(path, encoding="utf-8"))


def by_reference(query: str) -> None:
    norm = normalize_ref(query)
    if not norm:
        raise SystemExit(f'could not parse a Scripture reference from "{query}"')
    key = norm["chapter_key"] if norm["verse_start"] is None else norm["verse_keys"][0]
    index = _load("scripture_index.json")
    hits = index.get(key, [])
    if not hits:
        print(f'\nNo article in the corpus cites {norm["ref"]}.\n')
        return
    scope = "chapter" if norm["verse_start"] is None else "verse"
    print(f'\n{len(hits)} article(s) lean on {norm["ref"]} ({scope}):\n')
    for h in sorted(hits, key=lambda x: x["id"]):
        print(f'  [{h["citation"]}]  {h["title"]}')
        print(f'      cites: {h["ref"]}')
    print()


def by_article(query: str) -> None:
    refs = _load("article_refs.json")
    # accept an id ("summa.st.i.q2.a3") or a citation ("ST I, q.2, a.3")
    aid = query
    if query.upper().startswith("ST "):
        import re
        m = re.match(r"ST\s+(I-II|II-II|III|Suppl\.|I)\s*,\s*q\.(\d+)\s*,\s*a\.(\d+)", query, re.I)
        if not m:
            raise SystemExit(f'could not parse an ST citation from "{query}"')
        part = m.group(1).lower().rstrip(".")
        aid = f"summa.st.{part}.q{m.group(2)}.a{m.group(3)}"
    my = refs.get(aid)
    if not my:
        print(f"\n{aid}: no Scripture citations recorded (or unknown id).\n")
        return
    print(f"\n{aid} rests on {len(my)} Scripture reference(s):\n")
    for r in my:
        print(f"  {r}")
    print()


def top() -> None:
    s = _load("stats.json")
    print("\nMost-cited books in the Summa:\n")
    for b, c in s["most_cited_books"][:12]:
        print(f"  {c:>4}  {b}")
    print("\nMost-cited verses:\n")
    for v in s["most_cited_verses"][:12]:
        print(f"  {v['count']:>3}  {v['ref']}")
    print(f"\n({s['scripture_citations_parsed']} of {s['scripture_citations_total']} "
          f"citations resolved into the graph, {s['parse_rate']*100:.1f}%.)\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="*")
    ap.add_argument("--article", metavar="ID_OR_CITATION")
    ap.add_argument("--top", action="store_true")
    args = ap.parse_args()

    if args.top:
        top()
    elif args.article:
        by_article(args.article)
    elif args.query:
        by_reference(" ".join(args.query))
    else:
        ap.error("give a reference, --article, or --top")


if __name__ == "__main__":
    main()

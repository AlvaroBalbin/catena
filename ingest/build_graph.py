"""
Build the citation graph from the ingested corpus.

Every Scripture reference an article makes becomes an edge. The output lets you walk
the tradition: from a verse to every article that leans on it, and from an article
to the verses it rests on.

Output (data/graph/):
  scripture_index.json   verse/chapter key -> [ {article id, citation, title, ref} ]
  article_refs.json      article id -> [ normalized refs it makes ]
  stats.json             coverage + most-cited books and verses (+ unparsed report)

Run: python ingest/build_graph.py
"""

from __future__ import annotations

import glob
import json
import os
from collections import Counter, defaultdict

from scripture import normalize_ref

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMA = os.path.join(ROOT, "data", "summa")
OUT = os.path.join(ROOT, "data", "graph")


def main() -> None:
    os.makedirs(OUT, exist_ok=True)

    # verse-level and chapter-level indices: key -> list of citing articles
    scripture_index: dict[str, list] = defaultdict(list)
    article_refs: dict[str, list] = {}

    total = parsed = 0
    unparsed = Counter()
    book_counts = Counter()
    verse_counts = Counter()
    articles = 0

    for f in sorted(glob.glob(os.path.join(SUMMA, "summa-*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            n = json.loads(line)
            articles += 1
            aid, cit, title = n["id"], n["citation"], n.get("title", "")
            refs_here = []
            seen_keys: set[str] = set()
            for c in n.get("citations_out", []):
                if c.get("kind") != "scripture":
                    continue
                total += 1
                norm = normalize_ref(c["raw"])
                if not norm:
                    unparsed[c["raw"]] += 1
                    continue
                parsed += 1
                refs_here.append(norm["ref"])
                book_counts[norm["book"]] += 1
                # index this article under each verse key and the chapter key,
                # de-duplicated so one article is not listed twice for a range
                entry_keys = set(norm["verse_keys"]) | {norm["chapter_key"]}
                for vk in norm["verse_keys"]:
                    verse_counts[vk] += 1
                for k in entry_keys:
                    if k in seen_keys:
                        continue
                    seen_keys.add(k)
                    scripture_index[k].append(
                        {"id": aid, "citation": cit, "title": title, "ref": norm["ref"]}
                    )
            if refs_here:
                article_refs[aid] = sorted(set(refs_here))

    # stable ordering for reproducible output
    scripture_index_sorted = {k: scripture_index[k] for k in sorted(scripture_index)}

    with open(os.path.join(OUT, "scripture_index.json"), "w", encoding="utf-8") as fh:
        json.dump(scripture_index_sorted, fh, ensure_ascii=False, indent=0)
    with open(os.path.join(OUT, "article_refs.json"), "w", encoding="utf-8") as fh:
        json.dump(article_refs, fh, ensure_ascii=False, indent=0)

    def top_verses(n=25):
        out = []
        for vk, c in verse_counts.most_common(n):
            parts = vk.split("/")
            ref = f"{parts[0]} {parts[1]}:{parts[2]}" if len(parts) == 3 else vk
            out.append({"key": vk, "ref": ref, "count": c})
        return out

    stats = {
        "articles": articles,
        "scripture_citations_total": total,
        "scripture_citations_parsed": parsed,
        "parse_rate": round(parsed / total, 4) if total else 0,
        "unique_verse_keys": sum(1 for k in scripture_index if k.count("/") == 2),
        "unique_chapter_keys": sum(1 for k in scripture_index if k.count("/") == 1),
        "most_cited_books": book_counts.most_common(20),
        "most_cited_verses": top_verses(25),
        "unparsed_count": sum(unparsed.values()),
        "unparsed_top": unparsed.most_common(20),
    }
    with open(os.path.join(OUT, "stats.json"), "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)

    print(f"articles: {articles}")
    print(f"scripture citations: {parsed}/{total} parsed ({stats['parse_rate']*100:.1f}%)")
    print(f"verse nodes: {stats['unique_verse_keys']} | chapter nodes: {stats['unique_chapter_keys']}")
    print("most-cited books:", ", ".join(f"{b}({c})" for b, c in book_counts.most_common(8)))
    print("most-cited verses:", ", ".join(f"{v['ref']}({v['count']})" for v in top_verses(6)))


if __name__ == "__main__":
    main()

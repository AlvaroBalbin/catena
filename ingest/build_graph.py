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
from crossref import parse_internal_refs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMA = os.path.join(ROOT, "data", "summa")
CATENA = os.path.join(ROOT, "data", "catena")
CATECHISM = os.path.join(ROOT, "data", "catechism")
OUT = os.path.join(ROOT, "data", "graph")


def main() -> None:
    os.makedirs(OUT, exist_ok=True)

    # load all nodes first so internal references can be resolved against the full
    # id set (a reference to a not-yet-seen article must still resolve)
    nodes = []
    for f in sorted(glob.glob(os.path.join(SUMMA, "summa-*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            nodes.append(json.loads(line))
    meta = {n["id"]: {"citation": n["citation"], "title": n.get("title", "")} for n in nodes}
    id_set = set(meta)

    # verse-level and chapter-level indices: key -> list of citing articles
    scripture_index: dict[str, list] = defaultdict(list)
    article_refs: dict[str, list] = {}

    # internal article -> article edges
    internal_refs: dict[str, list] = {}
    internal_cited_by: dict[str, list] = defaultdict(list)
    internal_total = internal_resolved = 0
    in_degree = Counter()

    total = parsed = 0
    unparsed = Counter()
    book_counts = Counter()
    verse_counts = Counter()
    articles = 0

    for n in nodes:
            articles += 1
            aid, cit, title = n["id"], n["citation"], n.get("title", "")

            # internal cross-references (article -> article)
            targets = []
            for tid in parse_internal_refs(n["text"]):
                internal_total += 1
                if tid == aid or tid not in id_set:
                    continue
                internal_resolved += 1
                targets.append(tid)
            if targets:
                targets = list(dict.fromkeys(targets))
                internal_refs[aid] = [{"id": t, "citation": meta[t]["citation"]} for t in targets]
                for t in targets:
                    in_degree[t] += 1
                    internal_cited_by[t].append({"id": aid, "citation": cit, "title": title})

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

    internal_cited_by_sorted = {k: internal_cited_by[k] for k in sorted(internal_cited_by)}

    with open(os.path.join(OUT, "scripture_index.json"), "w", encoding="utf-8") as fh:
        json.dump(scripture_index_sorted, fh, ensure_ascii=False, indent=0)
    with open(os.path.join(OUT, "article_refs.json"), "w", encoding="utf-8") as fh:
        json.dump(article_refs, fh, ensure_ascii=False, indent=0)
    with open(os.path.join(OUT, "internal_refs.json"), "w", encoding="utf-8") as fh:
        json.dump(internal_refs, fh, ensure_ascii=False, indent=0)
    with open(os.path.join(OUT, "internal_cited_by.json"), "w", encoding="utf-8") as fh:
        json.dump(internal_cited_by_sorted, fh, ensure_ascii=False, indent=0)

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
        "internal_refs_total": internal_total,
        "internal_refs_resolved": internal_resolved,
        "internal_resolve_rate": round(internal_resolved / internal_total, 4) if internal_total else 0,
        "internal_edges": sum(len(v) for v in internal_refs.values()),
        "most_cited_articles": [
            {"citation": meta[i]["citation"], "title": meta[i]["title"], "in_degree": d}
            for i, d in in_degree.most_common(20)
        ],
    }
    with open(os.path.join(OUT, "stats.json"), "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)

    print(f"articles: {articles}")
    print(f"scripture citations: {parsed}/{total} parsed ({stats['parse_rate']*100:.1f}%)")
    print(f"verse nodes: {stats['unique_verse_keys']} | chapter nodes: {stats['unique_chapter_keys']}")
    print("most-cited books:", ", ".join(f"{b}({c})" for b, c in book_counts.most_common(8)))
    print("most-cited verses:", ", ".join(f"{v['ref']}({v['count']})" for v in top_verses(6)))
    print(f"internal edges: {stats['internal_edges']} "
          f"({internal_resolved}/{internal_total} refs resolved to real articles)")
    mca = stats["most_cited_articles"][:3]
    print("most-cited articles:", ", ".join(f"{a['citation']}({a['in_degree']})" for a in mca))

    build_catena_graph()
    build_catechism_graph()


def build_catena_graph() -> None:
    """Emit the golden-chain graph for the Catena Aurea, kept in SEPARATE files so
    the Summa's scripture_index.json (which test_graph.py asserts is Summa-only) is
    never touched:

      fathers_index.json          Gospel verse key -> [ {catena id, citation,
                                  father_summary, work} ] : from a verse, every
                                  pericope whose Fathers comment on it.
      catena_scripture_edges.json catena id -> [ normalized cross-ref strings ] :
                                  the Scripture the Fathers cite inside a pericope.
    """
    files = sorted(glob.glob(os.path.join(CATENA, "*.jsonl")))
    if not files:
        print("Catena: not ingested (graph skipped)")
        return

    nodes = []
    for f in files:
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if line:
                nodes.append(json.loads(line))

    fathers_index: dict[str, list] = defaultdict(list)
    scripture_edges: dict[str, list] = {}
    edge_total = 0

    for n in nodes:
        # distinct Fathers in this pericope, in first-appearance order
        fathers = list(dict.fromkeys(s["father"] for s in n.get("segments", [])))
        father_summary = ", ".join(fathers)
        entry = {
            "id": n["id"],
            "citation": n["citation"],
            "father_summary": father_summary,
            "work": "catena-aurea",
        }
        for vk in n.get("commented_verse_keys", []):
            fathers_index[vk].append(entry)

        refs = []
        seen: set[str] = set()
        for c in n.get("citations_out", []):
            if c.get("kind") != "scripture":
                continue
            norm = normalize_ref(c["raw"])
            ref = norm["ref"] if norm else c["raw"]
            if ref in seen:
                continue
            seen.add(ref)
            refs.append(ref)
        if refs:
            scripture_edges[n["id"]] = refs
            edge_total += len(refs)

    fathers_index_sorted = {k: fathers_index[k] for k in sorted(fathers_index)}
    scripture_edges_sorted = {k: scripture_edges[k] for k in sorted(scripture_edges)}

    with open(os.path.join(OUT, "fathers_index.json"), "w", encoding="utf-8") as fh:
        json.dump(fathers_index_sorted, fh, ensure_ascii=False, indent=0)
    with open(os.path.join(OUT, "catena_scripture_edges.json"), "w", encoding="utf-8") as fh:
        json.dump(scripture_edges_sorted, fh, ensure_ascii=False, indent=0)

    print(f"catena: {len(nodes)} pericopes, {len(fathers_index_sorted)} commented "
          f"verse keys indexed, {edge_total} Father scripture cross-ref edges")


def build_catechism_graph() -> None:
    """Emit the Roman Catechism's Scripture graph, kept in SEPARATE files so the
    Summa's scripture_index.json (which test_graph.py asserts is Summa-only) is never
    touched:

      catechism_scripture_edges.json  catechism id -> [ normalized ref strings ] : the
                                      Scripture the Catechism cites in that subsection.
      catechism_index.json            verse/chapter key -> [ {id, citation, title,
                                      work} ] : from a verse, every Catechism subsection
                                      that cites it (the "what does the Catechism teach
                                      citing this verse" join).

    Built entirely from each node's citations_out via the shared normalize_ref, exactly
    as the Summa graph is. Note: the McHugh-Callan edition quotes Scripture inline
    without chapter:verse markers, so citations_out is empty for this corpus and these
    files are therefore empty; the machinery is correct and will populate the moment a
    referenced edition is ingested (see ingest/catechism.py)."""
    files = sorted(glob.glob(os.path.join(CATECHISM, "*.jsonl")))
    if not files:
        print("catechism: not ingested (graph skipped)")
        return

    nodes = []
    for f in files:
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if line:
                nodes.append(json.loads(line))

    scripture_edges: dict[str, list] = {}
    index: dict[str, list] = defaultdict(list)
    edge_total = 0

    for n in nodes:
        refs = []
        seen_refs: set[str] = set()
        seen_keys: set[str] = set()
        for c in n.get("citations_out", []):
            if c.get("kind") != "scripture":
                continue
            norm = normalize_ref(c["raw"])
            if not norm:
                continue
            if norm["ref"] not in seen_refs:
                seen_refs.add(norm["ref"])
                refs.append(norm["ref"])
            entry_keys = set(norm["verse_keys"]) | {norm["chapter_key"]}
            for k in entry_keys:
                if k in seen_keys:
                    continue
                seen_keys.add(k)
                index[k].append({
                    "id": n["id"], "citation": n["citation"],
                    "title": n.get("title", ""), "work": "roman-catechism",
                })
        if refs:
            scripture_edges[n["id"]] = refs
            edge_total += len(refs)

    scripture_edges_sorted = {k: scripture_edges[k] for k in sorted(scripture_edges)}
    index_sorted = {k: index[k] for k in sorted(index)}

    with open(os.path.join(OUT, "catechism_scripture_edges.json"), "w", encoding="utf-8") as fh:
        json.dump(scripture_edges_sorted, fh, ensure_ascii=False, indent=0)
    with open(os.path.join(OUT, "catechism_index.json"), "w", encoding="utf-8") as fh:
        json.dump(index_sorted, fh, ensure_ascii=False, indent=0)

    note = "" if edge_total else " (inline chapter:verse refs absent in this edition)"
    print(f"catechism: {len(nodes)} subsections, {edge_total} scripture cross-ref "
          f"edges, {len(index_sorted)} cited verse keys indexed{note}")


if __name__ == "__main__":
    main()

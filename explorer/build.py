"""
Build the static explorer's data bundle.

The explorer (explorer/index.html) is a single self-contained page that runs entirely
in the browser over precomputed JSON - no server, no API, no build step at view time.
This script produces that JSON from the corpus in data/, as two files:

  explorer/data/core.json   (~1 MB gzipped)  loaded first: article titles, the whole
                            citation graph, and the verbatim text (English + Latin) of
                            every verse the Summa cites. Enough to browse the golden
                            chain, look up a verse in both languages, and search by
                            title - instantly.
  explorer/data/bodies.json (~4 MB gzipped)  loaded after: the full verbatim text of
                            every article, which upgrades search to full-text and lets
                            you read an article in full.

Nothing here is new source; it is a compact projection of data/ for the browser. Rerun
after any corpus change:  python explorer/build.py

Stdlib only.
"""

from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(HERE, "data")

sys.path.insert(0, os.path.join(ROOT, "ingest"))
from scripture import _BOOK_LOOKUP  # noqa: E402  (single source of truth for names)


def load_articles() -> list[dict]:
    arts = []
    for f in sorted(glob.glob(os.path.join(DATA, "summa", "*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if line:
                arts.append(json.loads(line))
    return arts


def load_graph(name: str):
    p = os.path.join(DATA, "graph", f"{name}.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def load_verse_text(subdir: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in glob.glob(os.path.join(DATA, "bible", subdir, "*.jsonl")):
        for line in open(f, encoding="utf-8"):
            d = json.loads(line)
            out[d["verse_key"]] = d["text"]
    return out


def load_catena() -> list[dict]:
    """The Catena Aurea pericopes (Aquinas's patristic golden chain on the 4 Gospels).
    Each node is one verse-pericope carrying an ordered list of Father-attributed
    fragments; keyed to Gospel verses via commented_verse_keys."""
    out = []
    for f in sorted(glob.glob(os.path.join(DATA, "catena", "*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_lectionary() -> dict:
    """date (YYYY-MM-DD) -> the day's Mass Gospel reference, so the explorer can show
    'the Fathers on today's Gospel'. Empty until data/lectionary/gospels.json exists."""
    p = os.path.join(DATA, "lectionary", "gospels.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def load_catechism() -> list[dict]:
    """The Roman Catechism (Catechism of the Council of Trent), one node per subsection.
    Doctrinal prose - folded into the searchable/readable passage set beside the Summa."""
    out = []
    for f in sorted(glob.glob(os.path.join(DATA, "catechism", "*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    arts = load_articles()
    # stable index order = order the articles are read; the graph references by id, so
    # the explorer resolves id -> index once on load.
    articles_meta = [[a["id"], a["citation"], a.get("title", "")] for a in arts]
    bodies = {a["id"]: a["text"] for a in arts}
    cit2id = {a["citation"]: a["id"] for a in arts}

    # Fold the Roman Catechism into the same searchable + readable passage set as the
    # Summa (it carries no citation graph yet, so it just reads as a cited teaching).
    catechism_nodes = load_catechism()
    for c in catechism_nodes:
        articles_meta.append([c["id"], c["citation"], c.get("title", "")])
        bodies[c["id"]] = c["text"]

    scripture_index = load_graph("scripture_index")
    stats = load_graph("stats")

    # the verbatim text (English + Latin) of every verse the Summa actually cites -
    # the payoff of the golden chain, small enough to ship in the core bundle.
    cited = [k for k in scripture_index if k.count("/") == 2]
    en = load_verse_text("drb")
    la = load_verse_text("vg")
    verses = {k: [en.get(k, ""), la.get(k, "")] for k in cited}
    # include the full text of the four Gospels (English + Latin), so "today's Gospel"
    # and the Fathers' chains read in full - not only the verses the Summa happens to cite.
    for k in en:
        if k.split("/")[0] in ("matthew", "mark", "luke", "john"):
            verses[k] = [en.get(k, ""), la.get(k, "")]

    # book name/abbreviation -> slug, straight from the citation normalizer, so the
    # explorer resolves "John 1:14", "Jn 1:14", "Osee 1" the same way the corpus does.
    book_slugs = {alias: slug for alias, (_name, slug) in _BOOK_LOOKUP.items()}
    slug_names = {slug: name for _alias, (name, slug) in _BOOK_LOOKUP.items()}

    # --- Catena Aurea: the patristic golden chain, verse-keyed ---------------------
    # fathers_index (verse_key -> pericopes) powers "the Fathers on this verse"; it is
    # small, so it rides in core. The full fragment text rides in a lazily-loaded
    # bundle (catena.json), like bodies.json, keyed by pericope id.
    catena = load_catena()
    fathers_index = load_graph("fathers_index")
    catena_bundle = {
        n["id"]: {
            "cit": n["citation"],
            "path": n.get("path", []),
            "lemma": n.get("lemma", ""),
            # [father, text] pairs, in the order Aquinas chained them
            "segs": [[s.get("father", ""), s["text"]] for s in n["segments"]],
            "refs": [c["raw"] for c in n.get("citations_out", [])],
        }
        for n in catena
    }
    distinct_fathers = {s.get("father", "") for n in catena for s in n["segments"]}
    distinct_fathers.discard("")
    fragments = sum(len(n["segments"]) for n in catena)
    # most-glossed Scripture: Gospel verses the Fathers weigh in on most heavily, by
    # number of distinct Fathers across the pericope(s) that comment on them.
    gloss_weight: dict[str, int] = {}
    for n in catena:
        nfathers = len({s.get("father", "") for s in n["segments"]} - {""})
        for vk in n.get("commented_verse_keys", []):
            gloss_weight[vk] = gloss_weight.get(vk, 0) + nfathers
    most_glossed = [
        {"key": k, "ref": f"{slug_names.get(k.split('/')[0], k.split('/')[0])} "
                          f"{k.split('/')[1]}:{k.split('/')[2]}", "count": c}
        for k, c in sorted(gloss_weight.items(), key=lambda kv: -kv[1])[:12]
    ]

    core = {
        "meta": {
            "articles": len(arts),
            "scripture_edges": stats.get("scripture_citations_parsed", 0),
            "internal_edges": stats.get("internal_edges", 0),
            "cited_verse_keys": stats.get("unique_verse_keys", len(cited)),
            "verses_en": len(en),
            "verses_la": len(la),
            "catena_pericopes": len(catena),
            "catena_fragments": fragments,
            "catena_fathers": len(distinct_fathers),
            "catechism_sections": len(catechism_nodes),
        },
        "book_slugs": book_slugs,
        "slug_names": slug_names,
        "articles": articles_meta,
        "scripture_index": scripture_index,
        "article_refs": load_graph("article_refs"),
        "internal_refs": load_graph("internal_refs"),
        "internal_cited_by": load_graph("internal_cited_by"),
        "fathers_index": fathers_index,
        "lectionary": load_lectionary(),
        "stats": {
            "most_cited_books": stats.get("most_cited_books", []),
            "most_cited_verses": stats.get("most_cited_verses", []),
            "most_glossed_verses": most_glossed,
            # enrich with the article id so the explorer can link straight to it
            "most_cited_articles": [
                {**a, "id": cit2id.get(a.get("citation"), "")}
                for a in stats.get("most_cited_articles", [])
            ],
        },
        "verses": verses,
    }

    core_path = os.path.join(OUT, "core.json")
    bodies_path = os.path.join(OUT, "bodies.json")
    catena_path = os.path.join(OUT, "catena.json")
    with open(core_path, "w", encoding="utf-8") as f:
        json.dump(core, f, ensure_ascii=False, separators=(",", ":"))
    with open(bodies_path, "w", encoding="utf-8") as f:
        json.dump(bodies, f, ensure_ascii=False, separators=(",", ":"))
    with open(catena_path, "w", encoding="utf-8") as f:
        json.dump(catena_bundle, f, ensure_ascii=False, separators=(",", ":"))

    for label, p in [("core", core_path), ("bodies", bodies_path), ("catena", catena_path)]:
        mb = os.path.getsize(p) / 1e6
        print(f"wrote explorer/data/{label}.json  ({mb:.2f} MB)")
    print(f"articles: {len(arts)}  cited verses (EN+LA): {len(verses)}  "
          f"scripture edges: {core['meta']['scripture_edges']}  "
          f"internal edges: {core['meta']['internal_edges']}")
    print(f"catena: {len(catena)} pericopes  {fragments} fragments  "
          f"{len(distinct_fathers)} Fathers  {len(fathers_index)} glossed verses")
    print(f"catechism: {len(catechism_nodes)} sections (searchable + readable)")


if __name__ == "__main__":
    main()

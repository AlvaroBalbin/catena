"""
Assemble the Hugging Face dataset bundle from the corpus in data/.

Catena's dataset is the deliverable; this projects it into the shape the Hugging Face
Hub and `datasets` expect - one flat JSONL per subset, plus tabular edge lists that make
the citation graph itself loadable - and writes a dataset card. Publish with:

  python ingest/build_hf.py <output_dir>
  # then upload <output_dir> to the Hub (see the push step in the session notes)

Subsets emitted (each a `config` in the card, loadable by name):
  summa                one row per Summa article (id, citation, title, text, part)
  douay_rheims         one row per Douay-Rheims verse (English)
  clementine_vulgate   one row per Clementine Vulgate verse (Latin, parallel key)
  scripture_edges      one row per (article -> Scripture verse) citation edge
  internal_edges       one row per (article -> article) citation edge

Also copies the raw graph adjacency JSON into graph/ as a bonus for graph users.
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


def _read_jsonl(path):
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            yield json.loads(line)


def _write_jsonl(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return sum(1 for _ in open(path, encoding="utf-8"))


def part_of(article_id: str) -> str:
    # summa.st.<part>.qN.aM
    try:
        return article_id.split(".")[2]
    except IndexError:
        return ""


def build_summa(out):
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, "summa", "*.jsonl"))):
        for d in _read_jsonl(f):
            rows.append({
                "id": d["id"],
                "citation": d["citation"],
                "part": part_of(d["id"]),
                "title": d.get("title", ""),
                "text": d["text"],
                "work": d.get("work", "summa-theologiae"),
                "license": (d.get("source") or {}).get("license", "public-domain"),
            })
    return _write_jsonl(rows, os.path.join(out, "summa.jsonl"))


def build_bible(subdir, fname, out, latin=False):
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, "bible", subdir, "*.jsonl"))):
        for d in _read_jsonl(f):
            row = {
                "id": d["id"],
                "citation": d["citation"],
                "book": d["book"],
                "chapter": d["chapter"],
                "verse": d["verse"],
                "verse_key": d["verse_key"],
                "text": d["text"],
                "license": (d.get("source") or {}).get("license", "public-domain"),
            }
            row["book_printed"] = d.get("latin_book") if latin else d.get("douay_book")
            if latin:
                row["lang"] = "la"
            rows.append(row)
    return _write_jsonl(rows, os.path.join(out, fname))


def build_scripture_edges(out):
    idx = json.load(open(os.path.join(DATA, "graph", "scripture_index.json"), encoding="utf-8"))
    rows = []
    for verse_key, arts in idx.items():
        if verse_key.count("/") != 2:      # verse-level edges only (skip chapter keys)
            continue
        for a in arts:
            rows.append({
                "article_id": a["id"],
                "article_citation": a["citation"],
                "verse_ref": a.get("ref", ""),
                "verse_key": verse_key,
            })
    return _write_jsonl(rows, os.path.join(out, "scripture_edges.jsonl"))


def build_internal_edges(out):
    internal = json.load(open(os.path.join(DATA, "graph", "internal_refs.json"), encoding="utf-8"))
    # source citation from the summa files
    cit = {}
    for f in glob.glob(os.path.join(DATA, "summa", "*.jsonl")):
        for d in _read_jsonl(f):
            cit[d["id"]] = d["citation"]
    rows = []
    for src, dsts in internal.items():
        for d in dsts:
            rows.append({
                "src_id": src,
                "src_citation": cit.get(src, ""),
                "dst_id": d["id"],
                "dst_citation": d["citation"],
            })
    return _write_jsonl(rows, os.path.join(out, "internal_edges.jsonl"))


def build_catechism(out):
    """One row per Roman Catechism subsection: its Part, its heading, and full verbatim
    text - the doctrinal spine, addressable and searchable."""
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, "catechism", "*.jsonl"))):
        for d in _read_jsonl(f):
            path = d.get("path", [])
            rows.append({
                "id": d["id"],
                "citation": d["citation"],
                "part": path[1] if len(path) > 1 else "",
                "title": d.get("title", ""),
                "text": d["text"],
                "work": d.get("work", "roman-catechism"),
                "license": (d.get("source") or {}).get("license", "public-domain"),
            })
    return _write_jsonl(rows, os.path.join(out, "roman_catechism.jsonl"))


def _catena_nodes():
    for f in sorted(glob.glob(os.path.join(DATA, "catena", "*.jsonl"))):
        yield from _read_jsonl(f)


def build_catena(out):
    """One row per Catena Aurea pericope: the verse it comments on, the Fathers in the
    chain, and their full verbatim commentary."""
    rows = []
    for d in _catena_nodes():
        fathers = list(dict.fromkeys(s.get("father", "") for s in d["segments"] if s.get("father")))
        path = d.get("path", [])
        rows.append({
            "id": d["id"],
            "citation": d["citation"],
            "gospel": path[1] if len(path) > 1 else "",
            "lemma": d.get("lemma", ""),
            "text": d["text"],
            "fathers": ", ".join(fathers),
            "n_fragments": len(d["segments"]),
            "commented_verse_keys": d.get("commented_verse_keys", []),
            "license": (d.get("source") or {}).get("license", "public-domain"),
        })
    return _write_jsonl(rows, os.path.join(out, "catena_aurea.jsonl"))


def build_father_edges(out):
    """The patristic golden chain as edges: one row per (Catena pericope -> Gospel verse
    it comments on), with the Fathers who speak. The inverse of scripture_edges for the
    Fathers - which Fathers weigh in on which verse."""
    rows = []
    for d in _catena_nodes():
        fathers = ", ".join(dict.fromkeys(s.get("father", "") for s in d["segments"] if s.get("father")))
        for vk in d.get("commented_verse_keys", []):
            slug, ch, v = vk.split("/")
            rows.append({
                "pericope_id": d["id"],
                "pericope_citation": d["citation"],
                "verse_key": vk,
                "verse_ref": f"{slug.capitalize()} {ch}:{v}",
                "fathers": fathers,
            })
    return _write_jsonl(rows, os.path.join(out, "father_edges.jsonl"))


def copy_graph(out):
    gdir = os.path.join(out, "graph")
    os.makedirs(gdir, exist_ok=True)
    for name in ["scripture_index", "article_refs", "internal_refs",
                 "internal_cited_by", "stats"]:
        src = os.path.join(DATA, "graph", f"{name}.json")
        if os.path.exists(src):
            with open(src, encoding="utf-8") as r, open(os.path.join(gdir, f"{name}.json"), "w", encoding="utf-8") as w:
                w.write(r.read())


CARD = """---
license: other
license_name: public-domain
language:
  - en
  - la
tags:
  - theology
  - catholic
  - christianity
  - aquinas
  - summa-theologica
  - church-fathers
  - catena-aurea
  - patristics
  - bible
  - vulgate
  - citations
  - knowledge-graph
  - retrieval
pretty_name: "Catena: an open, cited corpus of the Catholic tradition"
size_categories:
  - 10K<n<100K
configs:
  - config_name: summa
    data_files: summa.jsonl
  - config_name: catena_aurea
    data_files: catena_aurea.jsonl
  - config_name: roman_catechism
    data_files: roman_catechism.jsonl
  - config_name: douay_rheims
    data_files: douay_rheims.jsonl
  - config_name: clementine_vulgate
    data_files: clementine_vulgate.jsonl
  - config_name: scripture_edges
    data_files: scripture_edges.jsonl
  - config_name: father_edges
    data_files: father_edges.jsonl
  - config_name: internal_edges
    data_files: internal_edges.jsonl
---

# Catena: an open, cited corpus of the Catholic tradition

A clean, machine-readable, **public-domain** corpus of the Catholic tradition where
every unit of text carries a **canonical citation**, the text is stored **verbatim**
(never paraphrased or truncated), and the tradition's own **citation graph** is
included as loadable data. Built for grounded, cite-or-refuse retrieval.

Source, ingest code, a live web explorer, and an MCP grounding server:
**https://github.com/AlvaroBalbin/catena**

## Subsets

| config | rows | what |
|--------|------|------|
| `summa` | {n_summa} | The Summa Theologica of Thomas Aquinas, one row per article, with its canonical citation (`ST I, q.2, a.3`) and full verbatim text. |
| `catena_aurea` | {n_catena} | The Catena Aurea - Aquinas's patristic "golden chain" on the four Gospels, one row per verse-pericope: the verse commented on, the Church Fathers in the chain, and their full verbatim commentary. |
| `roman_catechism` | {n_cat} | The Roman Catechism (Catechism of the Council of Trent), one row per subsection, with its Part and heading and full verbatim text. Public-domain McHugh &amp; Callan translation (1923). |
| `douay_rheims` | {n_drb} | The Douay-Rheims Bible (Challoner revision), one row per verse, English. |
| `clementine_vulgate` | {n_vg} | The Clementine Vulgate (Sixto-Clementine, 1592), one row per verse, Latin - keyed identically to the Douay-Rheims so a citation resolves to both languages. |
| `scripture_edges` | {n_se} | The citation graph: one row per (Summa article -> Scripture verse) edge. |
| `father_edges` | {n_fe} | The patristic golden chain as edges: one row per (Catena Aurea pericope -> Gospel verse it comments on), with the Fathers who speak - which Fathers weigh in on which verse. |
| `internal_edges` | {n_ie} | The citation graph: one row per (Summa article -> Summa article) edge. |

```python
from datasets import load_dataset

summa   = load_dataset("TheAlvaroBalbin/catena", "summa")
fathers = load_dataset("TheAlvaroBalbin/catena", "catena_aurea")
verses  = load_dataset("TheAlvaroBalbin/catena", "douay_rheims")
latin   = load_dataset("TheAlvaroBalbin/catena", "clementine_vulgate")
edges   = load_dataset("TheAlvaroBalbin/catena", "scripture_edges")
```

Every verse shares a `verse_key` (`john/1/14`) across the two Bibles and the edge
tables, so the subsets join cleanly: an article's Scripture citations resolve to real
verse text in English and Latin.

## The three disciplines

1. **Lossless.** Text is captured verbatim from the source edition; only whitespace is
   normalized. Nothing is summarized or silently truncated.
2. **Addressable.** Every unit has a stable, canonical citation and a join key.
3. **Grounded.** The reference demo (in the GitHub repo) answers only from retrieved
   units, always cites, and refuses when the corpus does not contain the answer.

## Sources and rights

All texts are public domain by age and are redistributed with their edition attributed.
Full provenance and the per-text rights reasoning are in
[`data/SOURCES.md`](https://github.com/AlvaroBalbin/catena/blob/main/data/SOURCES.md).

- **Summa Theologica** - trans. Fathers of the English Dominican Province, 2nd rev. ed.
  (1920-22). Public domain.
- **Catena Aurea** - Aquinas's compilation of the Church Fathers on the Gospels, in the
  Oxford translation edited by J. H. Newman (1841-45). Public domain.
- **Roman Catechism** (Catechism of the Council of Trent) - tr. J. A. McHugh & C. J.
  Callan (1923); public domain in the US (pre-1929). A different work from the
  copyrighted modern Catechism, which is not included.
- **Douay-Rheims Bible** - Challoner revision (1749-52), via Project Gutenberg #1581.
  Public domain.
- **Clementine Vulgate** - Sixto-Clementine (1592); electronic edition by The Clementine
  Vulgate Project (ed. M. Tweedale, 2005), released to the public domain.

Copyrighted texts (the modern Catechism, modern Bible or encyclical translations) are
**not** included. The `license: other` tag denotes public-domain-by-age; there is no
rights holder to waive rights, and none is implied.

## Citation graph coverage

96.8% of the Summa's Scripture citations parse (8,491 of 8,768). Because a single
citation to a verse range or a whole chapter touches several verses, those expand to
{n_se} verse-level `article -> verse` edges here (`scripture_edges`); chapter-level
citations and the full adjacency maps are in `graph/`. 99% of the Summa's internal
cross-references resolve into {n_ie} `article -> article` edges (`internal_edges`).
The graph builder and coverage details are in the GitHub repository.
"""


def main():
    if len(sys.argv) < 2:
        print("usage: python ingest/build_hf.py <output_dir>")
        raise SystemExit(1)
    out = os.path.abspath(sys.argv[1])
    os.makedirs(out, exist_ok=True)

    n_summa = build_summa(out)
    n_catena = build_catena(out)
    n_cat = build_catechism(out)
    n_drb = build_bible("drb", "douay_rheims.jsonl", out, latin=False)
    n_vg = build_bible("vg", "clementine_vulgate.jsonl", out, latin=True)
    n_se = build_scripture_edges(out)
    n_fe = build_father_edges(out)
    n_ie = build_internal_edges(out)
    copy_graph(out)

    card = CARD.format(n_summa=f"{n_summa:,}", n_catena=f"{n_catena:,}", n_cat=f"{n_cat:,}",
                       n_drb=f"{n_drb:,}", n_vg=f"{n_vg:,}", n_se=f"{n_se:,}",
                       n_fe=f"{n_fe:,}", n_ie=f"{n_ie:,}")
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as f:
        f.write(card)

    print(f"wrote HF bundle to {out}")
    print(f"  summa: {n_summa}  catena_aurea: {n_catena}  roman_catechism: {n_cat}  "
          f"douay_rheims: {n_drb}  clementine_vulgate: {n_vg}")
    print(f"  scripture_edges: {n_se}  father_edges: {n_fe}  internal_edges: {n_ie}")


if __name__ == "__main__":
    main()

"""
Roman Catechism (Catechism of the Council of Trent) ingest.

Parses the Roman Catechism into Catena schema nodes, one node per SUBSECTION - a
single headed teaching unit within a Part (an analytical section such as "Meaning
Of This Article", "What They Forbid", "Why This Petition Is Placed First"). This is
the corpus's doctrinal spine: the Church's own post-Tridentine catechism, expounding
the Creed, the Sacraments, the Decalogue, and the Lord's Prayer.

Edition: the Rev. John A. McHugh, O.P. and Charles J. Callan, O.P. English
translation, first published 1923 (public domain in the US since 2019; see
data/SOURCES.md). The source is catholicapologetics.info, which reproduces the
McHugh-Callan text as clean per-section HTML with an <h3> heading for every
analytical subsection and <p> for each body paragraph - the same clean-HTML shape
the Catena ingest relies on, keyed to the four Parts of the Catechism.

Design goals, in priority order (identical to summa.py / catena.py / bible.py):
  1. Lossless    - every subsection paragraph is preserved verbatim; we only strip the
                   HTML wrappers, resolve entities, drop the edition's soft-hyphen
                   line-break markers, and collapse whitespace runs. No word is
                   summarized, reworded, or dropped, and the segments of every node
                   rejoin to its `text` exactly (asserted per node).
  2. Addressable - every node gets a stable id and a canonical citation locating it in
                   Part -> unit (Article / Sacrament / Commandment / Petition) ->
                   subsection.
  3. Complete    - all four Parts, and within them every one of the 12 Articles, 7
                   Sacraments, 10 Commandments, and 7 Petitions, or ingest fails loudly
                   (a partial catechism never ships).

An honest boundary on Scripture citations: unlike the Summa (New Advent hyperlinks)
and the Catena (Douay anchor links), this edition quotes Scripture inline WITHOUT
machine-readable chapter:verse references (the McHugh-Callan references are footnotes
that every clean digitisation of the text drops). So `citations_out` is populated only
from explicit inline "Book chapter:verse" references, of which this source has
essentially none; the field is present and correctly built, but empty for this text.
We do NOT reconstruct a citation graph from the OCR footnotes of a different
digitisation, because a wrong citation is worse than a missing one for this project.

Stdlib only, so the repo installs with nothing.

Run: python ingest/catechism.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
import html as _html
from dataclasses import dataclass, asdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(HERE, ".cache", "catechism")
OUT = os.path.join(ROOT, "data", "catechism")

# scripture.py lives beside this file; share the exact reference normalizer the rest
# of the pipeline uses, so any Scripture reference keys identically to the Bible corpus.
sys.path.insert(0, HERE)
from scripture import normalize_ref  # noqa: E402

RETRIEVED = "2026-07-10"
UA = "Catena/0.1 (open Catholic corpus; contact via github.com/AlvaroBalbin/catena)"
BASE = "http://www.catholicapologetics.info/thechurch/catechism/%s.shtml"

SOURCE = {
    "edition": "Catechism of the Council of Trent, tr. J. A. McHugh & C. J. Callan, 1923",
    "translator": "John A. McHugh, O.P. and Charles J. Callan, O.P.",
    "license": "public-domain",
    "url": "http://www.catholicapologetics.info/thechurch/catechism/",
    "retrieved": RETRIEVED,
}

# --- part / page model ----------------------------------------------------

# Roman numeral + display name of each of the four Parts.
PARTS = {
    1: ("I", "The Creed"),
    2: ("II", "The Sacraments"),
    3: ("III", "The Ten Commandments"),
    4: ("IV", "The Lord's Prayer"),
}

_ORD = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh",
        "Eighth", "Ninth", "Tenth"]

# The source page map. Each entry:
#   (stem, part, code, unit_label, unit_type, unit_nums)
# stem       = catholicapologetics filename stem (also the cache key).
# code       = stable, regex-safe id component for the unit within its Part.
# unit_type  = "article" | "sacrament" | "commandment" | "petition" | structural
#              ("intro" | "preface" | "conclusion").
# unit_nums  = the numbered unit(s) this page covers, for the completeness spec
#              (None for structural pages; a list because the ninth+tenth
#              Commandments share one page in this edition).
PAGES: list[tuple] = []

# Part I: prologue on faith, then the twelve Articles of the Creed.
PAGES.append(("ApostlesCreed00", 1, "prologue", "Prologue: On Faith and the Creed", "intro", None))
for _n in range(1, 13):
    PAGES.append((f"ApostlesCreed{_n:02d}", 1, f"art{_n}", f"Article {_n}", "article", [_n]))

# Part II: the Sacraments in general, then the seven Sacraments.
PAGES.append(("Holy7Sacraments", 2, "general", "On the Sacraments in General", "intro", None))
_SACR = [
    ("Holy7Sacraments-Baptism", "baptism", "The Sacrament of Baptism", 1),
    ("Holy7Sacraments-Confirmation", "confirmation", "The Sacrament of Confirmation", 2),
    ("Holy7Sacraments-Eucharist", "eucharist", "The Sacrament of the Holy Eucharist", 3),
    ("Holy7Sacraments-Penance", "penance", "The Sacrament of Penance", 4),
    ("Holy7Sacraments-Unction", "extreme-unction", "The Sacrament of Extreme Unction", 5),
    ("Holy7Sacraments-Orders", "holy-orders", "The Sacrament of Holy Orders", 6),
    ("Holy7Sacraments-Matrimony", "matrimony", "The Sacrament of Matrimony", 7),
]
for _stem, _code, _label, _num in _SACR:
    PAGES.append((_stem, 2, _code, _label, "sacrament", [_num]))

# Part III: the Decalogue in general, then the ten Commandments (the 9th and 10th
# are expounded together on one page in this edition).
PAGES.append(("TenCommandments", 3, "decalogue", "On the Decalogue", "intro", None))
_CMD = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth"]
for _i, _w in enumerate(_CMD, start=1):
    PAGES.append((f"TenCommandments-{_w}", 3, f"cmd{_i}", f"The {_ORD[_i-1]} Commandment", "commandment", [_i]))
PAGES.append(("TenCommandments-ninth-tenth", 3, "cmd9-10", "The Ninth and Tenth Commandments", "commandment", [9, 10]))

# Part IV: prayer in general, the opening address, the seven Petitions, the Amen.
PAGES.append(("TheLordsPrayer", 4, "on-prayer", "On Prayer", "intro", None))
PAGES.append(("TheLordsPrayer00", 4, "our-father", 'The Address: "Our Father Who Art in Heaven"', "preface", None))
for _n in range(1, 8):
    PAGES.append((f"TheLordsPrayer{_n:02d}", 4, f"pet{_n}", f"The {_ORD[_n-1]} Petition", "petition", [_n]))
PAGES.append(("TheLordsPrayerAmen", 4, "amen", "Conclusion: Amen", "conclusion", None))

# completeness spec: which numbered units MUST be present in each Part.
EXPECTED = {
    "article": set(range(1, 13)),      # Part I: 12 Articles
    "sacrament": set(range(1, 8)),     # Part II: 7 Sacraments
    "commandment": set(range(1, 11)),  # Part III: 10 Commandments
    "petition": set(range(1, 8)),      # Part IV: 7 Petitions
}


# --- html -> verbatim text ------------------------------------------------

_SOFT_HYPHEN = "­"          # print line-break hyphenation marker; not a real char
# two stray OCR marks the edition carries (a garbled quote / footnote fleck), removed
# so no non-ASCII noise leaks into the text. Everything else in the source is ASCII.
_STRAY = {"°": " ", "·": " "}
_TAG = re.compile(r"<[^>]+>")
_SSI = "[an error occurred while processing this directive]"


def clean(fragment: str) -> str:
    """Strip HTML wrappers, resolve entities, drop soft-hyphens and the two stray
    OCR marks, and collapse whitespace runs to single spaces. Words and punctuation
    are otherwise untouched - the same whitespace policy the rest of the corpus uses."""
    txt = _html.unescape(_TAG.sub(" ", fragment))
    txt = txt.replace(_SOFT_HYPHEN, "")
    for k, v in _STRAY.items():
        txt = txt.replace(k, v)
    return re.sub(r"\s+", " ", txt).strip()


_ELEM = re.compile(r"<(h3|p)\b[^>]*>(.*?)</\1>", re.S | re.I)


def elements(html: str) -> list[tuple[str, str]]:
    """The (tag, cleaned-text) sequence of every <h3> and <p> in document order,
    with empty nodes and the server-side-include error line dropped."""
    out: list[tuple[str, str]] = []
    for m in _ELEM.finditer(html):
        t = clean(m.group(2))
        if not t or t == _SSI:
            continue
        out.append((m.group(1).lower(), t))
    return out


# --- inline scripture references ------------------------------------------

# This edition quotes Scripture inline without chapter:verse markers, so in practice
# this matches nothing; it is kept so the field is correctly built and so any explicit
# "Book 3:16" reference a future source carries is captured. Deliberately conservative
# (requires the colon form) to never emit a wrong citation. normalize_ref validates the
# book, so a non-book like "verse 3:5" is refused.
_INLINE_REF = re.compile(
    r"\b((?:[1-4]\s)?[A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s(\d+):(\d+)(?:\s*[-–]\s*(\d+))?"
)


def scripture_refs(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for m in _INLINE_REF.finditer(text):
        book, ch, v1, v2 = m.group(1), m.group(2), m.group(3), m.group(4)
        raw = f"{book} {ch}:{v1}" + (f"-{v2}" if v2 else "")
        norm = normalize_ref(raw)
        if not norm:
            continue
        key = norm["ref"]
        if key in seen:
            continue
        seen.add(key)
        out.append({"raw": raw, "kind": "scripture", "target_id": None})
    return out


# --- node -----------------------------------------------------------------

@dataclass
class Node:
    id: str
    work: str
    citation: str
    title: str
    path: list
    type: str
    text: str
    segments: list
    citations_out: list
    source: dict


def _assert_lossless(node: Node) -> None:
    """The core invariant: the segments must reproduce the text exactly."""
    rejoined = "\n\n".join(s["text"] for s in node.segments)
    if rejoined != node.text:
        raise AssertionError(
            f"lossless invariant broken for {node.id}: segments do not rejoin to text"
        )
    if not node.text.strip():
        raise AssertionError(f"empty text for {node.id}")


def parse_page(stem: str, part: int, code: str, unit_label: str, html: str) -> list[Node]:
    """Parse one source page into its subsection nodes.

    The page is a flat run of <h3> headings and <p> paragraphs. The first heading of a
    unit page is the structural title (e.g. 'ARTICLE I : "I BELIEVE IN GOD..."'), which
    carries no body of its own; any such heading-only <h3> is folded forward as a
    leading segment of the next subsection that HAS body, so the Creed / Commandment /
    Petition text it holds is preserved verbatim rather than dropped. Every subsequent
    heading with body opens a subsection node."""
    roman, part_name = PARTS[part]
    node_path = ["Roman Catechism", f"Part {roman}: {part_name}", unit_label]

    # split the element run into (heading, [body paragraphs]) blocks
    pre: list[str] = []
    blocks: list[list] = []
    cur: list | None = None
    for kind, txt in elements(html):
        if kind == "h3":
            if cur is not None:
                blocks.append(cur)
            cur = [txt, []]
        else:
            (pre if cur is None else cur[1]).append(txt)
    if cur is not None:
        blocks.append(cur)

    nodes: list[Node] = []
    pending: list[str] = list(pre)  # heading-only text carried to the next body node
    idx = 0
    for title, body in blocks:
        if not body:
            pending.append(title)
            continue
        idx += 1
        segments = [{"role": "heading", "text": h} for h in pending]
        segments += [{"role": "paragraph", "text": p} for p in body]
        pending = []
        text = "\n\n".join(s["text"] for s in segments)
        node = Node(
            id=f"catechism.p{part}.{code}.s{idx:02d}",
            work="roman-catechism",
            citation=f"Roman Catechism, Part {roman}, {unit_label} : {title}",
            title=title,
            path=node_path,
            type="catechism",
            text=text,
            segments=segments,
            citations_out=scripture_refs(text),
            source=SOURCE,
        )
        _assert_lossless(node)
        nodes.append(node)

    # any heading-only <h3> left dangling at the very end attaches to the last node,
    # so nothing is dropped
    if pending and nodes:
        last = nodes[-1]
        last.segments += [{"role": "heading", "text": h} for h in pending]
        last.text = "\n\n".join(s["text"] for s in last.segments)
        _assert_lossless(last)

    if not nodes:
        raise AssertionError(f"no subsection nodes parsed from {stem}")
    return nodes


# --- fetching + caching ---------------------------------------------------

def get_page(stem: str) -> str:
    """Return a source page, fetching politely and caching to disk (cp1252, the
    edition's encoding) so re-runs never refetch. The cached file is the ground truth
    the parser reads."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"ca_{stem}.html")
    if os.path.exists(path) and os.path.getsize(path) > 500:
        return open(path, "rb").read().decode("cp1252")
    url = BASE % stem
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = urllib.request.urlopen(req, timeout=60).read()
    with open(path, "wb") as f:
        f.write(data)
    time.sleep(0.5)  # be a good guest
    return data.decode("cp1252")


# --- driver ---------------------------------------------------------------

def build() -> dict:
    os.makedirs(OUT, exist_ok=True)

    by_part: dict[int, list[Node]] = {1: [], 2: [], 3: [], 4: []}
    present: dict[str, set[int]] = {k: set() for k in EXPECTED}
    units_meta: dict[int, list[dict]] = {1: [], 2: [], 3: [], 4: []}

    for stem, part, code, unit_label, unit_type, unit_nums in PAGES:
        html = get_page(stem)
        nodes = parse_page(stem, part, code, unit_label, html)
        by_part[part].extend(nodes)
        if unit_type in present and unit_nums:
            present[unit_type].update(unit_nums)
        units_meta[part].append({
            "code": code, "label": unit_label, "type": unit_type,
            "subsections": len(nodes),
        })

    # completeness: every numbered unit of every Part must be present, or fail loudly
    problems: list[str] = []
    for part in (1, 2, 3, 4):
        if not by_part[part]:
            problems.append(f"Part {PARTS[part][0]} has no nodes")
    for utype, need in EXPECTED.items():
        missing = need - present[utype]
        if missing:
            problems.append(f"missing {utype}(s): {sorted(missing)}")
    if problems:
        raise SystemExit("COMPLETENESS FAILURE (Roman Catechism):\n  " + "\n  ".join(problems))

    # unique ids across the whole corpus
    all_ids = [n.id for part in (1, 2, 3, 4) for n in by_part[part]]
    if len(all_ids) != len(set(all_ids)):
        dupes = sorted({i for i in all_ids if all_ids.count(i) > 1})
        raise AssertionError(f"duplicate node ids: {dupes[:10]}")

    # write one file per Part
    for part in (1, 2, 3, 4):
        path = os.path.join(OUT, f"part{part}.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for n in by_part[part]:
                fh.write(json.dumps(asdict(n), ensure_ascii=False) + "\n")

    total = len(all_ids)
    cites = sum(len(n.citations_out) for part in (1, 2, 3, 4) for n in by_part[part])
    summary = {
        "parts": {part: len(by_part[part]) for part in (1, 2, 3, 4)},
        "total_nodes": total,
        "scripture_citations": cites,
        "units": units_meta,
    }
    _write_manifest(by_part, units_meta, present)
    for part in (1, 2, 3, 4):
        roman, name = PARTS[part]
        print(f"Part {roman} ({name}): {len(by_part[part])} subsection nodes")
    print(f"total: {total} subsection nodes, {cites} inline scripture citations")
    print(f"complete: 12 Articles, 7 Sacraments, 10 Commandments, 7 Petitions")
    return summary


def _write_manifest(by_part: dict, units_meta: dict, present: dict) -> None:
    parts_block = []
    for part in (1, 2, 3, 4):
        roman, name = PARTS[part]
        parts_block.append({
            "part": roman,
            "name": name,
            "file": f"data/catechism/part{part}.jsonl",
            "subsections": len(by_part[part]),
            "units": units_meta[part],
        })
    manifest = {
        "work": "roman-catechism",
        "title": "Catechism of the Council of Trent (Roman Catechism)",
        "author": "Catholic Church (issued by order of Pope St. Pius V, 1566)",
        "edition": "Catechism of the Council of Trent, tr. J. A. McHugh & C. J. Callan (1923)",
        "translator": "John A. McHugh, O.P. and Charles J. Callan, O.P.",
        "license": "public-domain",
        "source": "http://www.catholicapologetics.info/thechurch/catechism/",
        "retrieved": RETRIEVED,
        "structure": ["work", "part", "unit", "subsection"],
        "node_granularity": "one subsection (a headed analytical teaching unit within a Part)",
        "scripture_citations": (
            "This edition quotes Scripture inline without chapter:verse references (the "
            "McHugh-Callan references are footnotes dropped by every clean digitisation); "
            "citations_out is therefore empty. No citation graph is reconstructed from a "
            "different digitisation's OCR footnotes - a wrong citation is worse than none."
        ),
        "completeness": {
            "articles": sorted(present["article"]),
            "sacraments": sorted(present["sacrament"]),
            "commandments": sorted(present["commandment"]),
            "petitions": sorted(present["petition"]),
        },
        "parts": parts_block,
        "totals": {
            "subsections": sum(len(by_part[p]) for p in (1, 2, 3, 4)),
        },
    }
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    build()
    print("Roman Catechism ingest complete.")

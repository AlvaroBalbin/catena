"""
Catena Aurea ingest.

Parses the four-Gospel *Catena Aurea* (Aquinas's patristic "golden chain") into
Catena schema nodes, one node per PERICOPE - a single verse-range block of Gospel
text with its chain of Father fragments.

The text is John Henry Newman's Oxford translation (1841-45, public domain), taken
from ecatholic2000.com, whose per-chapter pages carry a uniform structure:

    <h3 id="C:V"><a href="/douay-rheims-bible/<book>.shtml#C:V">C:V-V</a></h3>
    <p>Ver. N. ...the Gospel verse text (the lemma)...</p>
    <p><strong>JEROME</strong>. (Hom. ...) ...a Father's comment...</p>
    <p><strong>RABANUS</strong>. ...the next Father...</p>
    ... until the next <h3>

Design goals, in priority order (identical to summa.py / bible.py):
  1. Lossless    - the Father fragments are preserved verbatim; we only strip HTML
                   wrappers, resolve entities, and collapse whitespace runs.
  2. Addressable - every node gets a stable id and a canonical citation, and is
                   keyed to the Gospel verses it comments (the golden-chain join key).
  3. Verifiable  - segments concatenate back to `text` exactly (asserted per node),
                   and every Gospel chapter must be present (completeness spec).

Verbatim fidelity was cross-checked against the pristine CCEL ThML edition of the
same Newman translation (Matthew, Mark) before ingest; see data/SOURCES.md.

Stdlib only, so the repo installs with nothing.

Run: python ingest/catena.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from dataclasses import dataclass, asdict
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(HERE, ".cache", "catena_html")
OUT = os.path.join(ROOT, "data", "catena")
DRB = os.path.join(ROOT, "data", "bible", "drb")

# scripture.py lives beside this file; import it directly so verse keys and
# cross-reference normalization are shared with the rest of the pipeline.
sys.path.insert(0, HERE)
from scripture import normalize_ref, resolve_book  # noqa: E402

RETRIEVED = "2026-07-10"
UA = "Mozilla/5.0 (catena-ingest; contact alvaro@socialgravity.ai)"
BASE = "https://www.ecatholic2000.com/catena/untitled-%02d.shtml"

# Gospel -> (slug, display book, first untitled-NN page, chapter count). The page
# numbers are sequential on ecatholic2000 and were each verified by the Douay book
# and chapter their <h3> anchors point to (see verify_page below).
GOSPELS = [
    ("matthew", "Matthew", 8, 28),
    ("mark", "Mark", 41, 16),
    ("luke", "Luke", 62, 24),
    ("john", "John", 89, 21),
]

# completeness spec: expected chapter count per gospel. A missing chapter raises.
COUNTS = {"matthew": 28, "mark": 16, "luke": 24, "john": 21}


def load_drb_gospel_keys() -> set[str]:
    """Valid Gospel verse keys from the already-ingested Douay-Rheims, so the
    golden-chain join keys only ever point at verses that actually exist. The DRB
    (like the Vulgate the Fathers read) uses Vulgate versification, whereas
    ecatholic2000's pericope labels occasionally carry a modern verse number at a
    chapter's end (e.g. Mark 4:41, absent in the Vulgate's 40-verse Mark 4). We key
    only to verses present here and report any label verse we cannot resolve."""
    keys: set[str] = set()
    for slug in COUNTS:
        path = os.path.join(DRB, f"{slug}.jsonl")
        if not os.path.exists(path):
            return set()  # DRB not ingested; skip clamping (validate.py still gates)
        for line in open(path, encoding="utf-8"):
            keys.add(json.loads(line)["verse_key"])
    return keys


DRB_KEYS = load_drb_gospel_keys()
DROPPED: list[str] = []  # label verse keys not present in the DRB, for transparency


# --- html -> verbatim text ------------------------------------------------

class _TextExtractor(HTMLParser):
    """Strips tags, keeps text verbatim. Entities are resolved by the parser
    (convert_charrefs defaults True in py3), so numeric/named refs survive as their
    real characters and the edition's curly quotes are kept as-is."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def html_to_text(fragment: str) -> str:
    p = _TextExtractor()
    p.feed(fragment)
    # collapse internal whitespace runs to single spaces; trim ends. Words and
    # punctuation are untouched.
    return re.sub(r"\s+", " ", p.text()).strip()


# --- father-name normalization -------------------------------------------

# ecatholic2000 already prints full names in uppercase (JEROME, PSEUDO-CHRYSOSTOM,
# CYRIL OF ALEXANDRIA, ...). The general rule below title-cases them and keeps small
# words ("of", "the") lowercase. The alias map covers abbreviated forms in case a
# page uses them, and pins a couple of clean display choices.
_SMALL = {"of", "the", "of."}
_ALIASES = {
    "pseudo-chrys": "Pseudo-Chrysostom",
    "chrys": "Chrysostom",
    "aug": "Augustine",
    "gloss": "Gloss",
    "hier": "Jerome",
    "greg": "Gregory",
    "ambr": "Ambrose",
    "orig": "Origen",
    "remig": "Remigius",
    "raban": "Rabanus",
    "theophyl": "Theophylact",
    "bede": "Bede",
}


def normalize_father(raw: str) -> str:
    raw = re.sub(r"\s+", " ", raw).strip().rstrip(".")
    low = raw.lower()
    if low in _ALIASES:
        return _ALIASES[low]
    toks = raw.split()
    out: list[str] = []
    for i, t in enumerate(toks):
        w = "-".join(p.capitalize() for p in t.split("-"))
        if i > 0 and t.lower() in _SMALL:
            w = t.lower()
        out.append(w)
    return " ".join(out)


# --- in-fragment scripture cross-references -------------------------------

# every <a> pointing into the site's Douay-Rheims tree is a Scripture citation the
# Father makes. The href gives the (Douay) book reliably; the anchor text gives the
# chapter:verse(-verse). Building the ref from the href's book avoids the Douay
# abbreviations in the anchor text ("Ez.", "Is.") that normalize_ref would miss.
_XREF = re.compile(
    r'<a\s+href="/douay-rheims-bible/([a-z0-9-]+)\.shtml#[^"]*"[^>]*>(.*?)</a>',
    re.I | re.S,
)
_NUMS = re.compile(r"(\d+)\s*:\s*(\d+)(?:\s*[-\u2013\u2014]\s*(\d+))?")


def collect_xrefs(frag_htmls: list[str]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for frag in frag_htmls:
        for m in _XREF.finditer(frag):
            rb = resolve_book(m.group(1))
            if not rb:
                continue
            book, _slug = rb
            txt = html_to_text(m.group(2))
            nm = _NUMS.search(txt)
            if nm:
                ch, v1, v2 = nm.group(1), nm.group(2), nm.group(3)
                raw = f"{book} {ch}:{v1}" + (f"-{v2}" if v2 else "")
            else:
                cm = re.search(r"\d+", txt)
                if not cm:
                    continue
                raw = f"{book} {cm.group(0)}"
            norm = normalize_ref(raw)
            if not norm:
                continue
            key = norm["ref"]
            if key in seen:
                continue
            seen.add(key)
            out.append({"raw": raw, "kind": "scripture", "target_id": None})
    return out


# --- page parsing ---------------------------------------------------------

_H3 = re.compile(
    r'<h3 id="([^"]+)">\s*<a href="/douay-rheims-bible/([a-z0-9-]+)\.shtml#[^"]*"'
    r'[^>]*>([^<]+)</a>\s*</h3>',
    re.I | re.S,
)
_P = re.compile(r"<p>(.*?)</p>", re.S)  # plain <p> only: the content paragraphs
_STRONG_START = re.compile(r"\s*<strong>(.*?)</strong>\s*[.,:]?\s*", re.I | re.S)
# leading Gospel-verse marker on a lemma paragraph: "Ver. 1." or "3-6." etc.
_VMARK = re.compile(r"^(?:Ver\.\s*)?\d+(?:\s*[-\u2013\u2014]\s*\d+)?\s*\.\s+", re.I)


@dataclass
class Node:
    id: str
    work: str
    citation: str
    title: str
    path: list
    type: str
    lemma: str
    text: str
    segments: list
    commented_verse_keys: list
    citations_out: list
    source: dict


def _strip_vmark(txt: str) -> str:
    return _VMARK.sub("", txt, count=1)


def parse_page(html: str, slug: str, book: str, chapter: int, url: str) -> list[Node]:
    """Parse one chapter page into pericope nodes."""
    source = {
        "edition": "Catena Aurea (Oxford, 1841-45), tr. J. H. Newman",
        "translator": "John Henry Newman",
        "license": "public-domain",
        "url": url,
        "retrieved": RETRIEVED,
    }

    matches = list(_H3.finditer(html))
    nodes: list[Node] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        block = html[start:end]
        disp = html_to_text(m.group(3))

        # verse range from the header label, canonicalized via scripture.py
        nm = _NUMS.search(disp) or re.search(r"(\d+)\s*:\s*(\d+)", disp)
        if not nm:
            raise ValueError(f"cannot parse pericope range {disp!r} on {url}")
        ch = int(nm.group(1))
        v1 = int(nm.group(2))
        v2 = int(nm.group(3)) if nm.lastindex and nm.group(3) else v1
        if ch != chapter:
            raise ValueError(f"pericope chapter {ch} != page chapter {chapter} on {url}")
        norm = normalize_ref(f"{book} {ch}:{v1}" + (f"-{v2}" if v2 != v1 else ""))
        if not norm:
            raise ValueError(f"could not normalize pericope {book} {ch}:{v1}-{v2}")

        # walk the paragraphs: lemma (pre-first-Father) then Father fragments, with
        # a no-bold paragraph after a Father appended to that Father (continuation).
        lemma_parts: list[str] = []
        segments: list[dict] = []
        frag_htmls: list[str] = []
        cur: dict | None = None
        for pm in _P.finditer(block):
            ph = pm.group(1)
            sm = _STRONG_START.match(ph)
            if sm:
                father = normalize_father(html_to_text(sm.group(1)))
                rest = ph[sm.end():]
                body = html_to_text(rest)
                cur = {"role": "father", "father": father, "text": body}
                segments.append(cur)
                frag_htmls.append(rest)
            else:
                txt = html_to_text(ph)
                if not txt:
                    continue
                if cur is None:
                    lemma_parts.append(_strip_vmark(txt))
                else:
                    cur["text"] = cur["text"] + "\n\n" + txt
                    frag_htmls.append(ph)

        if not segments:
            # a pericope with no Father fragment is not a citable comment node
            print(f"  WARN: {url} {book} {ch}:{v1} has no Father fragments; skipped")
            continue

        text = "\n\n".join(s["text"] for s in segments)
        lemma = " ".join(p for p in lemma_parts if p).strip()

        # golden-chain join keys: keep only verses that exist in the DRB (Vulgate
        # versification). Any label verse absent there is recorded, not silently
        # dropped. The start verse (used in the id) is always present.
        if DRB_KEYS:
            keys = [k for k in norm["verse_keys"] if k in DRB_KEYS]
            for k in norm["verse_keys"]:
                if k not in DRB_KEYS:
                    DROPPED.append(k)
        else:
            keys = norm["verse_keys"]

        node = Node(
            id=f"catena.{slug}.{ch}.{v1}",
            work="catena-aurea",
            citation=f"Catena Aurea, {norm['ref']}",
            title="",
            path=["Catena Aurea", f"Gospel of {book}", f"Chapter {ch}"],
            type="father-comment",
            lemma=lemma,
            text=text,
            segments=segments,
            commented_verse_keys=keys,
            citations_out=collect_xrefs(frag_htmls),
            source=source,
        )
        _assert_lossless(node)
        nodes.append(node)

    return nodes


def _assert_lossless(node: Node) -> None:
    """The core invariant: the segments must reproduce the text exactly."""
    rejoined = "\n\n".join(s["text"] for s in node.segments)
    if rejoined != node.text:
        raise AssertionError(
            f"lossless invariant broken for {node.id}: segments do not rejoin to text"
        )
    if not node.text.strip():
        raise AssertionError(f"empty text for {node.id}")


# --- fetching + caching ---------------------------------------------------

def get_page(nn: int) -> str:
    """Return a chapter page, fetching politely and caching to disk so re-runs do
    not refetch. Cached files are the ground truth the parser reads."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"untitled-{nn:02d}.shtml")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return open(path, encoding="utf-8").read()
    url = BASE % nn
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = urllib.request.urlopen(req, timeout=60).read()
    with open(path, "wb") as f:
        f.write(data)
    time.sleep(0.7)  # be polite
    return data.decode("utf-8")


def verify_page(html: str, slug: str, chapter: int, url: str) -> None:
    """Self-check the page really is this gospel's chapter, using its own <h3>
    anchors into the Douay-Rheims tree. If ecatholic2000 ever shifts a page or
    slips in an intro page, this raises loudly rather than mis-indexing text."""
    books: set[str] = set()
    chapters: set[int] = set()
    for m in _H3.finditer(html):
        rb = resolve_book(m.group(2))
        if rb:
            books.add(rb[1])
        chapters.add(int(m.group(1).split(":")[0]))
    if books != {slug} or chapters != {chapter}:
        raise ValueError(
            f"page verification failed for {url}: expected {slug} ch.{chapter}, "
            f"found books={books or '{}'} chapters={sorted(chapters)}. "
            "The ecatholic2000 page offset may have shifted; re-scout the anchors."
        )


# --- driver ---------------------------------------------------------------

def build() -> dict:
    os.makedirs(OUT, exist_ok=True)
    summary: dict = {}
    for slug, book, start, nch in GOSPELS:
        nodes: list[Node] = []
        for idx in range(nch):
            nn = start + idx
            chapter = idx + 1
            url = BASE % nn
            html = get_page(nn)
            verify_page(html, slug, chapter, url)
            nodes.extend(parse_page(html, slug, book, chapter, url))

        # completeness: every expected chapter must have produced at least one node
        present = sorted({n.path[-1] for n in nodes})
        got_chapters = {int(n.citation.split()[-1].split(":")[0]) for n in nodes}
        missing = set(range(1, COUNTS[slug] + 1)) - got_chapters
        if missing:
            raise AssertionError(f"{slug}: missing chapters {sorted(missing)}")

        # unique ids within the gospel
        ids = [n.id for n in nodes]
        if len(ids) != len(set(ids)):
            dupes = [i for i in ids if ids.count(i) > 1]
            raise AssertionError(f"{slug}: duplicate node ids {sorted(set(dupes))[:10]}")

        path = os.path.join(OUT, f"{slug}.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for n in nodes:
                fh.write(json.dumps(asdict(n), ensure_ascii=False) + "\n")

        frags = sum(len(n.segments) for n in nodes)
        fathers = {s["father"] for n in nodes for s in n.segments}
        verses = {vk for n in nodes for vk in n.commented_verse_keys}
        summary[slug] = {
            "book": book,
            "chapters": len(got_chapters),
            "pericopes": len(nodes),
            "fragments": frags,
            "fathers": sorted(fathers),
            "commented_verses": len(verses),
            "file": f"data/catena/{slug}.jsonl",
        }
        print(f"{book}: {len(nodes)} pericopes, {frags} fragments, "
              f"{len(present)} chapters, {len(verses)} commented verses")
    return summary


if __name__ == "__main__":
    build()
    if DROPPED:
        uniq = sorted(set(DROPPED))
        print(f"note: {len(uniq)} label verse(s) absent in the DRB's Vulgate "
              f"numbering, dropped from join keys: {uniq}")
    print("Catena Aurea ingest complete.")

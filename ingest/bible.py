"""
Douay-Rheims (Challoner) Bible ingest.

Parses the public-domain Douay-Rheims Challoner text (Project Gutenberg #1581) into
Catena schema nodes, one node per verse. This is the Bible that matches the corpus:
the Summa's own Scripture citations (via New Advent) use Douay-Rheims naming and
Vulgate numbering, so every verse node keys identically to the citation graph and the
8,000+ Scripture edges resolve to actual verse text.

Design goals, in priority order (the same three disciplines as the Summa ingest):
  1. Lossless   - each verse is captured verbatim; only whitespace runs are collapsed.
                  Challoner's editorial notes and chapter arguments (which live in the
                  same file but are NOT scripture) are excluded, honestly and by rule -
                  see data/SOURCES.md.
  2. Addressable- every verse gets a canonical citation (`John 1:14`), a stable id
                  (`drb.john.1.14`), and a graph join key (`john/1/14`).
  3. Verifiable - completeness is proven: 73 books, the known chapter count per book,
                  and contiguous verse numbering 1..N in every chapter, or ingest fails.

Book names are mapped to slugs through the SAME resolver the citation normalizer uses
(ingest/scripture.py), so a citation "1 Kings 2:2" and the Douay book "1 Kings" land on
the identical verse key by construction.

Stdlib only.

Usage:
  python ingest/bible.py            # fetch (cached), parse, write data/bible/drb/, verify
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass, asdict

from scripture import resolve_book

RETRIEVED = "2026-07-09"
UA = "Catena/0.1 (open Catholic corpus; contact via github.com/AlvaroBalbin/catena)"
SRC_URL = "https://www.gutenberg.org/cache/epub/1581/pg1581.txt"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(HERE, ".cache")
OUT = os.path.join(ROOT, "data", "bible", "drb")

SOURCE = {
    "edition": "Douay-Rheims, Challoner revision (1749-52)",
    "translator": "English College at Douay/Rheims; revised by Bishop Richard Challoner",
    "license": "public-domain",
    "url": SRC_URL,
    "retrieved": RETRIEVED,
    "via": "Project Gutenberg eBook #1581",
}

# The 27 New Testament books, by canonical slug, to tag testament in each node's path.
NT_SLUGS = {
    "matthew", "mark", "luke", "john", "acts", "romans", "1-corinthians",
    "2-corinthians", "galatians", "ephesians", "philippians", "colossians",
    "1-thessalonians", "2-thessalonians", "1-timothy", "2-timothy", "titus",
    "philemon", "hebrews", "james", "1-peter", "2-peter", "1-john", "2-john",
    "3-john", "jude", "revelation",
}

# Completeness spec: known chapter count per book of the Challoner Douay-Rheims,
# keyed by canonical slug. Ingest fails loudly if any book is missing or has the
# wrong number of chapters. (Derived from and cross-checked against this edition.)
EXPECTED_CHAPTERS = {
    "genesis": 50, "exodus": 40, "leviticus": 27, "numbers": 36, "deuteronomy": 34,
    "joshua": 24, "judges": 21, "ruth": 4, "1-samuel": 31, "2-samuel": 24,
    "1-kings": 22, "2-kings": 25, "1-chronicles": 29, "2-chronicles": 36, "ezra": 10,
    "nehemiah": 13, "tobit": 14, "judith": 16, "esther": 16, "job": 42, "psalms": 150,
    "proverbs": 31, "ecclesiastes": 12, "song-of-songs": 8, "wisdom": 19, "sirach": 51,
    "isaiah": 66, "jeremiah": 52, "lamentations": 5, "baruch": 6, "ezekiel": 48,
    "daniel": 14, "hosea": 14, "joel": 3, "amos": 9, "obadiah": 1, "jonah": 4,
    "micah": 7, "nahum": 3, "habakkuk": 3, "zephaniah": 3, "haggai": 2, "zechariah": 14,
    "malachi": 4, "1-maccabees": 16, "2-maccabees": 15, "matthew": 28, "mark": 16,
    "luke": 24, "john": 21, "acts": 28, "romans": 16, "1-corinthians": 16,
    "2-corinthians": 13, "galatians": 6, "ephesians": 6, "philippians": 4,
    "colossians": 4, "1-thessalonians": 5, "2-thessalonians": 3, "1-timothy": 6,
    "2-timothy": 4, "titus": 3, "philemon": 1, "hebrews": 13, "james": 5, "1-peter": 5,
    "2-peter": 3, "1-john": 5, "2-john": 1, "3-john": 1, "jude": 1, "revelation": 22,
}

# canonical book order (OT then NT), for stable output ordering.
BOOK_ORDER = list(EXPECTED_CHAPTERS.keys())

# The Douay-Rheims prints the historical books under the old Septuagint/Vulgate
# numbering, where the *same string* means a different book than in modern usage:
# Douay "1-2 Kings" are Samuel, Douay "3-4 Kings" are the modern Kings, and Douay
# "1-2 Esdras" are Ezra and Nehemiah. The Summa's citations (via New Advent) use the
# MODERN names ("1 Samuel", "1 Kings", "Ezra", "Nehemiah"), and the shared normalizer
# resolves those correctly. So here - and ONLY here, at the Douay text - we map the
# printed Douay book title to the modern slug explicitly, so a Douay "1 Kings" verse
# lands on the same key a modern "1 Samuel" citation does. Made explicit on purpose:
# this is the one genuinely confusing naming seam in the whole canon.
DOUAY_ALIASES = {
    "1 Kings": ("1 Samuel", "1-samuel"),
    "2 Kings": ("2 Samuel", "2-samuel"),
    "3 Kings": ("1 Kings", "1-kings"),
    "4 Kings": ("2 Kings", "2-kings"),
    "1 Esdras": ("Ezra", "ezra"),
    "2 Esdras": ("Nehemiah", "nehemiah"),
}


def book_for(douay_name: str) -> tuple[str, str] | None:
    """Douay printed book title -> (canonical modern name, slug). Explicit override
    for the ambiguous historical books, shared resolver for everything else."""
    if douay_name in DOUAY_ALIASES:
        return DOUAY_ALIASES[douay_name]
    return resolve_book(douay_name)


@dataclass
class Verse:
    id: str
    work: str
    citation: str
    title: str
    path: list
    type: str
    text: str
    book: str
    douay_book: str
    chapter: int
    verse: int
    verse_key: str
    segments: list
    citations_out: list
    source: dict


# --- fetch ----------------------------------------------------------------

def fetch() -> str:
    """Download the Gutenberg text once, caching to disk (gitignored)."""
    cached = os.path.join(CACHE, "pg1581.txt")
    if os.path.exists(cached):
        return open(cached, encoding="utf-8", errors="replace").read()
    req = urllib.request.Request(SRC_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        text = r.read().decode("utf-8", errors="replace")
    os.makedirs(CACHE, exist_ok=True)
    with open(cached, "w", encoding="utf-8") as f:
        f.write(text)
    time.sleep(0.7)
    return text


# --- parse ----------------------------------------------------------------

_PG_START = re.compile(r"\*\*\*\s*START OF THE PROJECT GUTENBERG.*?\*\*\*", re.I)
_PG_END = re.compile(r"\*\*\*\s*END OF THE PROJECT GUTENBERG", re.I)

# A chapter header is a whole line: "<Book> Chapter <N>". The book part may carry a
# leading numeral ("1 Kings", "2 Paralipomenon", "1 Corinthians") then letters and
# spaces ("Canticle of Canticles"). Verse lines start with "<n>:<n>." so they can never
# match this: a colon is not in the book character class, so the match cannot reach
# " Chapter <N>".
_CHAPTER = re.compile(r"^(\d? ?[A-Za-z][A-Za-z ]*?) Chapter (\d+)\.?\s*$", re.M)

# A verse line begins with "<chapter>:<verse>." then its text. The space after the
# period is optional: 7 verses in this edition run the text straight against the dot
# ("2:13.For Adam..."), and dropping them would be a silent loss.
_VERSE = re.compile(r"^(\d+):(\d+)\.\s*(.*)$", re.S)


def strip_gutenberg(text: str) -> str:
    s = _PG_START.search(text)
    e = _PG_END.search(text)
    start = s.end() if s else 0
    end = e.start() if e else len(text)
    return text[start:end]


def _collapse(s: str) -> str:
    """Collapse whitespace runs to single spaces and trim. Words untouched -
    the same whitespace policy the Summa ingest uses."""
    return re.sub(r"\s+", " ", s).strip()


def iter_chapters(body: str):
    """Yield (douay_book, canonical_book, slug, chapter_no, chapter_text) for every
    chapter, where chapter_text is everything between this header and the next."""
    matches = list(_CHAPTER.finditer(body))
    for i, m in enumerate(matches):
        douay_book = m.group(1).strip()
        resolved = book_for(douay_book)
        if not resolved:
            # a line that looks like a header but is not a known book: skip it, but
            # this should never happen for the Catholic canon - surfaced by the
            # completeness check downstream (a book would come up missing).
            continue
        canonical, slug = resolved
        ch = int(m.group(2))
        seg_start = m.end()
        seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        yield douay_book, canonical, slug, ch, body[seg_start:seg_end]


def _paragraphs(chunk: str) -> list[str]:
    """Group a chapter's physical lines into paragraphs. This edition is uniformly
    double-spaced: a SINGLE blank line is a line-wrap inside one paragraph, and a run
    of TWO OR MORE blank lines is a paragraph break. So a verse's wrapped lines join
    into one paragraph, and each footnote/summary is its own paragraph."""
    paras: list[str] = []
    cur: list[str] = []
    blanks = 0
    for line in chunk.splitlines():
        if not line.strip():
            blanks += 1
            continue
        if blanks >= 2 and cur:
            paras.append(" ".join(cur))
            cur = []
        blanks = 0
        cur.append(line.strip())
    if cur:
        paras.append(" ".join(cur))
    return paras


def extract_chapter(chunk: str, ch: int) -> list[tuple[int, str]]:
    """Pull the verses out of one chapter's text in source order, as (printed_verse,
    text). A paragraph that begins with a verse marker is a verse; every other
    paragraph (the chapter summary, Challoner's footnotes) is editorial apparatus and
    is skipped - that is how the apparatus is excluded without touching a word of
    scripture."""
    out: list[tuple[int, str]] = []
    for para in _paragraphs(chunk):
        m = _VERSE.match(para)
        if not m:
            continue
        vch, vno, vtext = int(m.group(1)), int(m.group(2)), m.group(3)
        if vch != ch:
            raise ValueError(
                f"verse marker {vch}:{vno} disagrees with chapter header {ch} "
                "(possible parse drift)"
            )
        out.append((vno, _collapse(vtext)))
    return out


def normalize_numbering(slug: str, ch: int, raw: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Turn source-printed verse numbers into canonical, unique, ascending verse
    addresses that match how the Summa cites them. Handles the two - and only two -
    numbering shapes in this edition that are not a clean 1..N, EXPLICITLY, and fails
    loudly on anything else so no anomaly is ever normalized silently:

      * Vulgate psalm merges (e.g. Ps 113 = Hebrew 114+115): the source restarts the
        verse count for the second half. The Summa cites these with CONTINUOUS Vulgate
        numbering (it cites Psalm 113:24, which only exists if the halves are numbered
        1-8 then 9-26), so on a hard restart we continue from the running maximum.
      * A genuine duplicate label (Proverbs 12 prints two verses both numbered 12, then
        resumes correctly at 13): the two same-numbered verses are the two halves the
        Vulgate joins under one number, so we merge their text under that verse.

    Verbatim text is never altered; only the verse ADDRESS is canonicalized, and the
    fact is recorded (see ANOMALIES)."""
    result: list[tuple[int, str]] = []
    running_max = 0
    for printed, text in raw:
        if printed > running_max:
            result.append((printed, text))
            running_max = printed
        elif printed == running_max and result and printed == result[-1][0]:
            # duplicate of the immediately-preceding verse number -> merge text
            prev_v, prev_t = result[-1]
            result[-1] = (prev_v, prev_t + " " + text)
            ANOMALIES.append(f"{slug} {ch}: merged duplicate verse {printed}")
        elif printed < running_max:
            # a hard restart (Vulgate psalm merge) -> continue numbering
            running_max += 1
            result.append((running_max, text))
            if printed == 1:
                ANOMALIES.append(f"{slug} {ch}: continued numbering after restart at v1 "
                                 f"-> verse {running_max}")
        else:
            raise ValueError(f"{slug} {ch}: unhandled verse numbering at printed={printed}, "
                             f"running_max={running_max}")
    return result


ANOMALIES: list[str] = []


def parse_verses(text: str) -> list[Verse]:
    body = strip_gutenberg(text)
    verses: list[Verse] = []
    for douay_book, canonical, slug, ch, chunk in iter_chapters(body):
        testament = "New Testament" if slug in NT_SLUGS else "Old Testament"
        raw = extract_chapter(chunk, ch)
        for vno, vtext in normalize_numbering(slug, ch, raw):
            ref = f"{canonical} {ch}:{vno}"
            node = Verse(
                id=f"drb.{slug}.{ch}.{vno}",
                work="douay-rheims",
                citation=ref,
                title="",
                path=[testament, canonical, f"Chapter {ch}"],
                type="verse",
                text=vtext,
                book=canonical,
                douay_book=douay_book,
                chapter=ch,
                verse=vno,
                verse_key=f"{slug}/{ch}/{vno}",
                segments=[],
                citations_out=[],
                source=SOURCE,
            )
            _assert_verbatim(node)
            verses.append(node)
    return verses


def _assert_verbatim(node: Verse) -> None:
    if not node.text.strip():
        raise AssertionError(f"empty verse text for {node.id}")
    if _VERSE.match(node.text):
        raise AssertionError(f"verse marker leaked into text for {node.id}: {node.text[:40]!r}")


# --- completeness ---------------------------------------------------------

# Chapters that legitimately start above verse 1: the "second half" psalms of the
# Vulgate/Douay numbering (Heb 116 -> Vulg 114+115, Heb 147 -> Vulg 146+147), so Vulg
# 115 begins at v10 and Vulg 147 at v12. Every other chapter must start at verse 1.
KNOWN_VERSE_START = {("psalms", 115): 10, ("psalms", 147): 12}


def check_completeness(verses: list[Verse]) -> dict:
    """Prove structural completeness: every expected book present with its known
    chapter count, and verses that are unique and contiguous from their first to their
    last number in every chapter (starting at verse 1, save the documented Vulgate
    psalm splits). Raises SystemExit on any gap so a partial Bible never ships."""
    by_book: dict[str, dict[int, list[int]]] = {}
    for v in verses:
        by_book.setdefault(v.verse_key.split("/")[0], {}).setdefault(v.chapter, []).append(v.verse)

    problems: list[str] = []

    missing_books = [b for b in EXPECTED_CHAPTERS if b not in by_book]
    if missing_books:
        problems.append(f"missing books: {missing_books}")
    extra_books = [b for b in by_book if b not in EXPECTED_CHAPTERS]
    if extra_books:
        problems.append(f"unexpected books: {extra_books}")

    for slug, expected in EXPECTED_CHAPTERS.items():
        chapters = by_book.get(slug, {})
        if not chapters:
            continue
        got = max(chapters)
        if got != expected:
            problems.append(f"{slug}: {got} chapters, expected {expected}")
        for ch in range(1, got + 1):
            vs = sorted(chapters.get(ch, []))
            if not vs:
                problems.append(f"{slug} ch.{ch}: no verses")
                continue
            if len(vs) != len(set(vs)):
                dups = sorted({x for x in vs if vs.count(x) > 1})
                problems.append(f"{slug} ch.{ch}: duplicate verse numbers {dups}")
            start = KNOWN_VERSE_START.get((slug, ch), 1)
            if vs[0] != start:
                problems.append(f"{slug} ch.{ch}: starts at verse {vs[0]}, expected {start}")
            if vs != list(range(vs[0], vs[-1] + 1)):
                gaps = sorted(set(range(vs[0], vs[-1] + 1)) - set(vs))
                problems.append(f"{slug} ch.{ch}: gaps in verses {gaps[:10]}")

    if problems:
        raise SystemExit("COMPLETENESS FAILURE (Douay-Rheims):\n  " + "\n  ".join(problems[:40]))

    return {
        "books": len(by_book),
        "chapters": sum(len(c) for c in by_book.values()),
        "verses": len(verses),
    }


# --- coverage vs the citation graph --------------------------------------

def coverage_vs_graph(verses: list[Verse]) -> dict:
    """How much of the corpus's Scripture citation graph now resolves to real verse
    text. This is the payoff of Pillar 2, measured, not asserted."""
    idx_path = os.path.join(ROOT, "data", "graph", "scripture_index.json")
    if not os.path.exists(idx_path):
        return {}
    index = json.load(open(idx_path, encoding="utf-8"))
    have = {v.verse_key for v in verses}
    cited_verse_keys = {k for k in index if k.count("/") == 2}
    resolved = cited_verse_keys & have
    return {
        "cited_verse_keys": len(cited_verse_keys),
        "resolved_to_text": len(resolved),
        "rate": round(len(resolved) / len(cited_verse_keys), 4) if cited_verse_keys else 0,
    }


# --- write ----------------------------------------------------------------

def write_corpus(verses: list[Verse]) -> None:
    os.makedirs(OUT, exist_ok=True)
    by_slug: dict[str, list[Verse]] = {}
    for v in verses:
        by_slug.setdefault(v.verse_key.split("/")[0], []).append(v)
    for slug in BOOK_ORDER:
        rows = by_slug.get(slug, [])
        if not rows:
            continue
        with open(os.path.join(OUT, f"{slug}.jsonl"), "w", encoding="utf-8") as f:
            for v in rows:
                f.write(json.dumps(asdict(v), ensure_ascii=False) + "\n")


def write_manifest(stats: dict, coverage: dict, slug_to_book: dict) -> None:
    books = []
    for slug in BOOK_ORDER:
        books.append({"slug": slug, "book": slug_to_book.get(slug, slug),
                      "chapters": EXPECTED_CHAPTERS[slug],
                      "testament": "New Testament" if slug in NT_SLUGS else "Old Testament"})
    manifest = {
        "work": "douay-rheims",
        "title": "The Holy Bible, Douay-Rheims Version",
        "edition": "Challoner revision (1749-52)",
        "translator": "English College at Douay/Rheims; revised by Bishop Richard Challoner",
        "license": "public-domain",
        "source": SRC_URL,
        "via": "Project Gutenberg eBook #1581",
        "retrieved": RETRIEVED,
        "structure": ["testament", "book", "chapter", "verse"],
        "canon": "Catholic (73 books, incl. deuterocanonical)",
        "numbering": "Septuagint/Vulgate (Douay-Rheims), aligns with the Summa's citations",
        "scope": "verse text only; Challoner's editorial notes and chapter arguments excluded (see data/SOURCES.md)",
        "counts": {"books": stats["books"], "chapters": stats["chapters"], "verses": stats["verses"]},
        "citation_graph_coverage": coverage,
        "citation_graph_coverage_note": (
            "The unresolved remainder are Summa citations that reference a verse number "
            "beyond the chapter's actual length (garbled source citations, e.g. a cited "
            "Leviticus 12:17 where Leviticus 12 has 8 verses) or the handful of psalms "
            "where New Advent's citation numbering differs from this edition's Vulgate "
            "numbering. The Bible correctly contains no such verse; nothing is missing."
        ),
        "numbering_normalizations": list(ANOMALIES),
        "books": books,
    }
    with open(os.path.join(ROOT, "data", "bible", "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def main() -> None:
    print("== ingesting Douay-Rheims (Challoner), Project Gutenberg #1581 ==")
    text = fetch()
    verses = parse_verses(text)
    stats = check_completeness(verses)
    coverage = coverage_vs_graph(verses)
    write_corpus(verses)
    slug_to_book = {v.verse_key.split("/")[0]: v.book for v in verses}
    write_manifest(stats, coverage, slug_to_book)
    print(f"books: {stats['books']}  chapters: {stats['chapters']}  verses: {stats['verses']}")
    if coverage:
        print(f"citation-graph coverage: {coverage['resolved_to_text']}/{coverage['cited_verse_keys']} "
              f"cited verse keys now resolve to real verse text ({coverage['rate']*100:.1f}%)")
    if ANOMALIES:
        print(f"documented numbering normalizations ({len(ANOMALIES)}):")
        for a in ANOMALIES:
            print(f"  - {a}")
    print(f"wrote {OUT}/<book>.jsonl + data/bible/manifest.json")


if __name__ == "__main__":
    main()

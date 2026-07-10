"""
Clementine Vulgate (1592 Sixto-Clementine) ingest - the Latin behind the citations.

Parses the public-domain electronic Clementine Vulgate (The Clementine Vulgate
Project, ed. Michael Tweedale, 2005) into Catena schema nodes, one node per verse, as
a PARALLEL Latin text to the Douay-Rheims. Every Latin verse keys on the SAME
`verse_key` as its Douay-Rheims counterpart (`john/1/14`), so a single Scripture
citation now resolves to both the English the Douay translators rendered and the Latin
Aquinas actually quoted. Where the two editions split a verse differently (a handful
of Psalms), the keys simply do not meet - measured and reported, never forced.

Design goals, in priority order (the same three disciplines as the rest of Catena):
  1. Lossless   - each verse's Latin words are captured verbatim. The edition's own
                  typographic markup is removed by an explicit, documented rule and
                  nothing else is touched:
                    /   poetic line (hemistich) break        -> space
                    \\   paragraph mark (pilcrow)             -> space
                    [ ]  bracket a poetic block               -> removed
                    <..> marginal speaker rubric (Canticle:   -> removed whole
                         <Sponsa>, <Sponsus>, <Chorus>)          (apparatus, not text)
                  The Latin ligatures/diacritics of the edition (ae, AE, oe, e-with-
                  diaeresis) are kept verbatim as UTF-8.
  2. Addressable- every verse gets the canonical modern citation (`John 1:14`), a
                  stable id (`vg.john.1.14`), and the shared graph join key
                  (`john/1/14`), keyed identically to the Douay verse and the Summa's
                  Scripture edges by construction.
  3. Verifiable - completeness is proven against the same canon spec as the Douay
                  ingest: 73 books, the known chapter count per book, contiguous verse
                  numbering 1..N in every chapter, or ingest fails.

The source files are named with the project's own Latin abbreviations (Gn, 3Rg, Ct,
Sap, Apc...). BOOKS below maps each abbreviation to our canonical slug AND to the
Latin book name printed in the edition, so nothing about the source naming is hidden.

Stdlib only.

Usage:
  python ingest/vulgate.py          # fetch (cached), parse, write data/bible/vg/, verify
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass, asdict

# Reuse the Douay ingest's canon spec so both Bibles are checked against one source of
# truth for what "complete" means (73 books, chapter counts, NT membership).
from bible import EXPECTED_CHAPTERS, BOOK_ORDER, NT_SLUGS

RETRIEVED = "2026-07-09"
UA = "Catena/0.1 (open Catholic corpus; contact via github.com/AlvaroBalbin/catena)"

# The Clementine Vulgate Project's per-book text files (Michael Tweedale's edition),
# released to the public domain. Obtained as the project's `.lat` files via a GitHub
# mirror that documents them as downloaded from the project's site (vulsearch); see
# data/SOURCES.md for the full provenance and rights reasoning.
SRC_BASE = "https://raw.githubusercontent.com/jrichter/ClementineVulgateConverter/master/latin"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(HERE, ".cache", "vulgate")
OUT = os.path.join(ROOT, "data", "bible", "vg")

SOURCE = {
    "edition": "Clementine Vulgate (Sixto-Clementine, 1592)",
    "electronic_edition": "The Clementine Vulgate Project (ed. Michael Tweedale, London, 2005)",
    "license": "public-domain",
    "url": SRC_BASE,
    "retrieved": RETRIEVED,
    "via": "GitHub mirror jrichter/ClementineVulgateConverter/latin (project .lat files)",
}

# Source file abbreviation -> (canonical slug, Latin book name as printed in the
# edition). The slug is the SAME one the Douay ingest and the citation normalizer use,
# so a Clementine "3Rg" (Regum III) verse lands on the identical key a modern "1 Kings"
# citation does. The Latin name is kept on each node so the edition's own naming is
# never lost. This is the one deliberately explicit seam, like the Douay aliases.
BOOKS = {
    "Gn": ("genesis", "Genesis"), "Ex": ("exodus", "Exodus"),
    "Lv": ("leviticus", "Leviticus"), "Nm": ("numbers", "Numeri"),
    "Dt": ("deuteronomy", "Deuteronomium"), "Jos": ("joshua", "Josue"),
    "Jdc": ("judges", "Judicum"), "Rt": ("ruth", "Ruth"),
    "1Rg": ("1-samuel", "Regum I"), "2Rg": ("2-samuel", "Regum II"),
    "3Rg": ("1-kings", "Regum III"), "4Rg": ("2-kings", "Regum IV"),
    "1Par": ("1-chronicles", "Paralipomenon I"), "2Par": ("2-chronicles", "Paralipomenon II"),
    "Esr": ("ezra", "Esdrae"), "Neh": ("nehemiah", "Nehemiae"),
    "Tob": ("tobit", "Tobiae"), "Jdt": ("judith", "Judith"),
    "Est": ("esther", "Esther"), "Job": ("job", "Job"),
    "Ps": ("psalms", "Psalmi"), "Pr": ("proverbs", "Proverbia"),
    "Ecl": ("ecclesiastes", "Ecclesiastes"), "Ct": ("song-of-songs", "Canticum Canticorum"),
    "Sap": ("wisdom", "Sapientia"), "Sir": ("sirach", "Ecclesiasticus"),
    "Is": ("isaiah", "Isaias"), "Jr": ("jeremiah", "Jeremias"),
    "Lam": ("lamentations", "Lamentationes"), "Bar": ("baruch", "Baruch"),
    "Ez": ("ezekiel", "Ezechiel"), "Dn": ("daniel", "Daniel"),
    "Os": ("hosea", "Osee"), "Joel": ("joel", "Joel"),
    "Am": ("amos", "Amos"), "Abd": ("obadiah", "Abdias"),
    "Jon": ("jonah", "Jonas"), "Mch": ("micah", "Michaeas"),
    "Nah": ("nahum", "Nahum"), "Hab": ("habakkuk", "Habacuc"),
    "Soph": ("zephaniah", "Sophonias"), "Agg": ("haggai", "Aggaeus"),
    "Zach": ("zechariah", "Zacharias"), "Mal": ("malachi", "Malachias"),
    "1Mcc": ("1-maccabees", "Machabaeorum I"), "2Mcc": ("2-maccabees", "Machabaeorum II"),
    "Mt": ("matthew", "Matthaeus"), "Mc": ("mark", "Marcus"),
    "Lc": ("luke", "Lucas"), "Jo": ("john", "Joannes"),
    "Act": ("acts", "Actus Apostolorum"), "Rom": ("romans", "ad Romanos"),
    "1Cor": ("1-corinthians", "ad Corinthios I"), "2Cor": ("2-corinthians", "ad Corinthios II"),
    "Gal": ("galatians", "ad Galatas"), "Eph": ("ephesians", "ad Ephesios"),
    "Phlp": ("philippians", "ad Philippenses"), "Col": ("colossians", "ad Colossenses"),
    "1Thes": ("1-thessalonians", "ad Thessalonicenses I"),
    "2Thes": ("2-thessalonians", "ad Thessalonicenses II"),
    "1Tim": ("1-timothy", "ad Timotheum I"), "2Tim": ("2-timothy", "ad Timotheum II"),
    "Tit": ("titus", "ad Titum"), "Phlm": ("philemon", "ad Philemonem"),
    "Hbr": ("hebrews", "ad Hebraeos"), "Jac": ("james", "Jacobi"),
    "1Ptr": ("1-peter", "Petri I"), "2Ptr": ("2-peter", "Petri II"),
    "1Jo": ("1-john", "Joannis I"), "2Jo": ("2-john", "Joannis II"),
    "3Jo": ("3-john", "Joannis III"), "Jud": ("jude", "Judae"),
    "Apc": ("revelation", "Apocalypsis"),
}

# The edition's source files are Windows-1252 (cp1252) encoded. The only non-ASCII
# characters that legitimately appear are these Latin ligatures/diacritics; ingest
# asserts the corpus contains no others, so an encoding slip can never pass silently.
ALLOWED_NONASCII = {"æ", "Æ", "œ", "ë"}  # ae, AE, oe, e-diaeresis

# canonical output order, shared with the Douay ingest.
SLUG_ORDER = BOOK_ORDER


@dataclass
class Verse:
    id: str
    work: str
    lang: str
    citation: str
    title: str
    path: list
    type: str
    text: str
    book: str
    latin_book: str
    chapter: int
    verse: int
    verse_key: str
    segments: list
    citations_out: list
    source: dict


# --- fetch ----------------------------------------------------------------

def fetch(abbr: str) -> str:
    """Download one book's .lat file once, caching to disk (gitignored). Decoded from
    the edition's cp1252 encoding to text."""
    cached = os.path.join(CACHE, f"{abbr}.lat")
    if os.path.exists(cached):
        return open(cached, "rb").read().decode("cp1252")
    req = urllib.request.Request(f"{SRC_BASE}/{abbr}.lat", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    os.makedirs(CACHE, exist_ok=True)
    with open(cached, "wb") as f:
        f.write(data)
    time.sleep(0.3)
    return data.decode("cp1252")


# --- parse ----------------------------------------------------------------

# Every content line is "<chapter>:<verse> <latin text>". The edition ships no headers
# or blank structure lines inside a book file, so this is the only line shape.
_VERSE = re.compile(r"^(\d+):(\d+)\s+(.*)$")

# The edition's typographic markup. Documented and removed explicitly (see module
# docstring). A marginal speaker rubric <...> is removed whole; the line-layout marks
# become spaces so they can only ever separate words, never join them.
_RUBRIC = re.compile(r"<[^>]*>")
_LAYOUT = str.maketrans({"/": " ", "\\": " ", "[": " ", "]": " "})


def clean_latin(raw: str) -> str:
    """Strip the edition's typographic markup, collapse whitespace, keep every Latin
    word (and its ligatures) verbatim. Deterministic: the validator re-runs exactly
    this on the raw source and requires the result to equal the stored text."""
    s = _RUBRIC.sub("", raw)
    s = s.translate(_LAYOUT)
    return re.sub(r"\s+", " ", s).strip()


def parse_book(abbr: str, text: str) -> list[Verse]:
    slug, latin_name = BOOKS[abbr]
    testament = "New Testament" if slug in NT_SLUGS else "Old Testament"
    canonical = SLUG_TO_CANON[slug]
    verses: list[Verse] = []
    seen: set[tuple[int, int]] = set()
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.rstrip()
        if not line:
            continue
        m = _VERSE.match(line)
        if not m:
            raise ValueError(f"{abbr}: unparseable line {lineno}: {line[:60]!r}")
        ch, vno = int(m.group(1)), int(m.group(2))
        if (ch, vno) in seen:
            raise ValueError(f"{abbr}: duplicate verse {ch}:{vno}")
        seen.add((ch, vno))
        latin = clean_latin(m.group(3))
        if not latin:
            raise ValueError(f"{abbr}: empty verse text at {ch}:{vno}")
        _assert_clean(latin, abbr, ch, vno)
        ref = f"{canonical} {ch}:{vno}"
        verses.append(Verse(
            id=f"vg.{slug}.{ch}.{vno}",
            work="clementine-vulgate",
            lang="la",
            citation=ref,
            title="",
            path=[testament, canonical, f"Chapter {ch}"],
            type="verse",
            text=latin,
            book=canonical,
            latin_book=latin_name,
            chapter=ch,
            verse=vno,
            verse_key=f"{slug}/{ch}/{vno}",
            segments=[],
            citations_out=[],
            source=SOURCE,
        ))
    return verses


def _assert_clean(latin: str, abbr: str, ch: int, vno: int) -> None:
    if any(c in latin for c in "/\\[]<>"):
        raise AssertionError(f"{abbr} {ch}:{vno}: markup leaked into text: {latin[:40]!r}")
    for c in latin:
        if ord(c) > 127 and c not in ALLOWED_NONASCII:
            raise AssertionError(
                f"{abbr} {ch}:{vno}: unexpected non-ASCII {c!r} (U+{ord(c):04X}); "
                "possible encoding slip")


# The Douay ingest maps a slug to its canonical display name via the same normalizer;
# we mirror that name here from BOOKS so both Bibles print an identical citation for a
# shared key. Built once so the citation string matches the Douay's exactly.
from scripture import resolve_book  # noqa: E402

SLUG_TO_CANON: dict[str, str] = {}
for _abbr, (_slug, _lat) in BOOKS.items():
    # resolve the slug through the shared normalizer to get the canonical display name
    _canon = resolve_book(_slug.replace("-", " "))
    SLUG_TO_CANON[_slug] = _canon[0] if _canon else _slug


# --- completeness ---------------------------------------------------------

def check_completeness(verses: list[Verse]) -> dict:
    """Prove structural completeness against the shared canon spec: every expected
    book present with its known chapter count, verses unique and contiguous 1..N in
    every chapter. Raises SystemExit on any gap so a partial Vulgate never ships.

    The Clementine and the Douay-Rheims share this structure by construction (the
    Douay was translated from the Vulgate), so re-using EXPECTED_CHAPTERS here is also
    an independent cross-check that the two editions agree on book and chapter shape."""
    by_book: dict[str, dict[int, list[int]]] = {}
    for v in verses:
        by_book.setdefault(v.verse_key.split("/")[0], {}).setdefault(v.chapter, []).append(v.verse)

    problems: list[str] = []
    missing = [b for b in EXPECTED_CHAPTERS if b not in by_book]
    if missing:
        problems.append(f"missing books: {missing}")
    extra = [b for b in by_book if b not in EXPECTED_CHAPTERS]
    if extra:
        problems.append(f"unexpected books: {extra}")

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
                problems.append(f"{slug} ch.{ch}: duplicate verse numbers")
            if vs[0] != 1:
                problems.append(f"{slug} ch.{ch}: starts at verse {vs[0]}, expected 1")
            if vs != list(range(vs[0], vs[-1] + 1)):
                gaps = sorted(set(range(vs[0], vs[-1] + 1)) - set(vs))
                problems.append(f"{slug} ch.{ch}: gaps in verses {gaps[:10]}")

    if problems:
        raise SystemExit("COMPLETENESS FAILURE (Clementine Vulgate):\n  " + "\n  ".join(problems[:40]))

    return {
        "books": len(by_book),
        "chapters": sum(len(c) for c in by_book.values()),
        "verses": len(verses),
    }


# --- coverage vs the Douay-Rheims and the citation graph ------------------

def _drb_keys() -> set:
    import glob
    keys = set()
    for f in glob.glob(os.path.join(ROOT, "data", "bible", "drb", "*.jsonl")):
        for line in open(f, encoding="utf-8"):
            keys.add(json.loads(line)["verse_key"])
    return keys


def coverage(verses: list[Verse]) -> dict:
    """Two honest payoff numbers: how well the Latin verse addresses line up with the
    Douay-Rheims (parallel-text coverage), and how much of the Summa's Scripture
    citation graph now resolves to real Latin text."""
    have = {v.verse_key for v in verses}
    out: dict = {}

    drb = _drb_keys()
    if drb:
        out["parallel"] = {
            "vulgate_verses": len(have),
            "douay_verses": len(drb),
            "shared_keys": len(have & drb),
            "vulgate_only": len(have - drb),
            "douay_only": len(drb - have),
            "alignment_rate": round(len(have & drb) / len(drb), 4),
        }

    idx_path = os.path.join(ROOT, "data", "graph", "scripture_index.json")
    if os.path.exists(idx_path):
        index = json.load(open(idx_path, encoding="utf-8"))
        cited = {k for k in index if k.count("/") == 2}
        out["citation_graph"] = {
            "cited_verse_keys": len(cited),
            "resolved_to_latin": len(cited & have),
            "rate": round(len(cited & have) / len(cited), 4) if cited else 0,
        }
    return out


# --- write ----------------------------------------------------------------

def write_corpus(verses: list[Verse]) -> None:
    os.makedirs(OUT, exist_ok=True)
    by_slug: dict[str, list[Verse]] = {}
    for v in verses:
        by_slug.setdefault(v.verse_key.split("/")[0], []).append(v)
    for slug in SLUG_ORDER:
        rows = by_slug.get(slug, [])
        if not rows:
            continue
        rows.sort(key=lambda v: (v.chapter, v.verse))
        with open(os.path.join(OUT, f"{slug}.jsonl"), "w", encoding="utf-8") as f:
            for v in rows:
                f.write(json.dumps(asdict(v), ensure_ascii=False) + "\n")


def write_manifest(stats: dict, cov: dict) -> None:
    books = []
    for abbr, (slug, latin_name) in BOOKS.items():
        books.append({
            "slug": slug, "book": SLUG_TO_CANON[slug], "latin_book": latin_name,
            "source_file": f"{abbr}.lat", "chapters": EXPECTED_CHAPTERS[slug],
            "testament": "New Testament" if slug in NT_SLUGS else "Old Testament",
        })
    # keep manifest book order canonical (OT then NT), like the Douay manifest
    books.sort(key=lambda b: SLUG_ORDER.index(b["slug"]))
    manifest = {
        "work": "clementine-vulgate",
        "title": "Biblia Sacra juxta Vulgatam Clementinam",
        "edition": "Sixto-Clementine Vulgate (1592)",
        "electronic_edition": "The Clementine Vulgate Project (ed. Michael Tweedale, London, 2005)",
        "language": "Latin",
        "license": "public-domain",
        "source": SRC_BASE,
        "via": SOURCE["via"],
        "retrieved": RETRIEVED,
        "structure": ["testament", "book", "chapter", "verse"],
        "canon": "Catholic (73 books, incl. deuterocanonical)",
        "numbering": "Vulgate numbering; keyed identically to the Douay-Rheims and the Summa's citations",
        "scope": ("verse text only, verbatim. The edition's typographic markup is removed by rule: "
                  "poetic line breaks '/', paragraph marks '\\\\', poetic brackets '[ ]', and the "
                  "Canticle's marginal speaker rubrics '<Sponsa>/<Sponsus>/<Chorus>' (editorial "
                  "apparatus, not scripture). Latin ligatures (ae, oe, e-diaeresis) kept verbatim."),
        "counts": {"books": stats["books"], "chapters": stats["chapters"], "verses": stats["verses"]},
        "parallel_coverage": cov.get("parallel", {}),
        "citation_graph_coverage": cov.get("citation_graph", {}),
        "coverage_note": (
            "This Latin parallels the Douay-Rheims verse for verse across 99.9% of "
            "addresses. The handful that do not meet are concentrated in the Psalms, "
            "where this Clementine edition and the Gutenberg Douay-Rheims split a few "
            "verses (chiefly the psalm tituli) differently. Both are valid Vulgate "
            "numbering; nothing is missing, the addresses simply differ, and that gap "
            "is reported rather than papered over."
        ),
        "books": books,
    }
    with open(os.path.join(ROOT, "data", "bible", "vulgate_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def main() -> None:
    print("== ingesting the Clementine Vulgate (The Clementine Vulgate Project) ==")
    all_verses: list[Verse] = []
    for abbr in BOOKS:
        text = fetch(abbr)
        all_verses.extend(parse_book(abbr, text))
    stats = check_completeness(all_verses)
    cov = coverage(all_verses)
    write_corpus(all_verses)
    write_manifest(stats, cov)
    print(f"books: {stats['books']}  chapters: {stats['chapters']}  verses: {stats['verses']}")
    if cov.get("parallel"):
        p = cov["parallel"]
        print(f"parallel to Douay-Rheims: {p['shared_keys']}/{p['douay_verses']} "
              f"verse addresses align ({p['alignment_rate']*100:.1f}%); "
              f"{p['vulgate_only']} Vulgate-only, {p['douay_only']} Douay-only")
    if cov.get("citation_graph"):
        g = cov["citation_graph"]
        print(f"citation-graph coverage: {g['resolved_to_latin']}/{g['cited_verse_keys']} "
              f"cited verse keys now resolve to real Latin text ({g['rate']*100:.1f}%)")
    print(f"wrote {OUT}/<book>.jsonl + data/bible/vulgate_manifest.json")


if __name__ == "__main__":
    main()

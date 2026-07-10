"""
Resolve a Scripture reference to the actual verse text - English and Latin.

Before this, the citation graph could tell you WHICH articles lean on John 1:14; now
it can also hand you the verse itself, verbatim and cited: the Douay-Rheims English and,
in parallel, the Clementine Vulgate Latin Aquinas actually quoted. Zero-dependency,
lazy: the verse text loads from data/bible/ on first use, and everything degrades
gracefully to "no verse text" if a Bible has not been ingested.
"""

from __future__ import annotations

import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRB = os.path.join(ROOT, "data", "bible", "drb")
VG = os.path.join(ROOT, "data", "bible", "vg")

_VERSES: dict[str, dict] | None = None
_LATIN: dict[str, dict] | None = None


def load_verses() -> dict[str, dict]:
    """verse_key ('john/1/14') -> {text, citation, book, chapter, verse}."""
    global _VERSES
    if _VERSES is None:
        _VERSES = {}
        for f in glob.glob(os.path.join(DRB, "*.jsonl")):
            for line in open(f, encoding="utf-8"):
                d = json.loads(line)
                _VERSES[d["verse_key"]] = {
                    "text": d["text"], "citation": d["citation"],
                    "book": d["book"], "chapter": d["chapter"], "verse": d["verse"],
                }
    return _VERSES


def load_latin() -> dict[str, dict]:
    """verse_key ('john/1/14') -> {text, latin_book} of Clementine Vulgate Latin."""
    global _LATIN
    if _LATIN is None:
        _LATIN = {}
        for f in glob.glob(os.path.join(VG, "*.jsonl")):
            for line in open(f, encoding="utf-8"):
                d = json.loads(line)
                _LATIN[d["verse_key"]] = {"text": d["text"], "latin_book": d["latin_book"]}
    return _LATIN


def latin_for(norm: dict) -> dict[str, str]:
    """Given a normalized reference, return {verse_key -> Latin text} for the Clementine
    Vulgate, so a consumer can print the Latin beside its English verse. Empty if the
    Vulgate is not ingested or the reference has no Latin address (a rare Psalm split)."""
    la = load_latin()
    if not la:
        return {}
    if norm["verse_start"] is None:
        prefix = norm["chapter_key"] + "/"
        return {k: d["text"] for k, d in la.items() if k.startswith(prefix)}
    return {k: la[k]["text"] for k in norm["verse_keys"] if k in la}


def verses_for(norm: dict) -> list[dict]:
    """Given a normalized reference (from scripture.normalize_ref), return the verse
    dicts that resolve to real text, in verse order. A chapter reference returns the
    whole chapter; a verse or range returns those verses. Empty if none are present."""
    v = load_verses()
    if not v:
        return []
    if norm["verse_start"] is None:
        prefix = norm["chapter_key"] + "/"
        return sorted((d for k, d in v.items() if k.startswith(prefix)),
                      key=lambda x: x["verse"])
    return [v[k] for k in norm["verse_keys"] if k in v]

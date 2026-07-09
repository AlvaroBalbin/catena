"""
Resolve a Scripture reference to the actual Douay-Rheims verse text.

Before this, the citation graph could tell you WHICH articles lean on John 1:14; now
it can also hand you the verse itself, verbatim and cited. Zero-dependency, lazy: the
verse text loads from data/bible/drb/ on first use, and everything degrades gracefully
to "no verse text" if the Bible has not been ingested.
"""

from __future__ import annotations

import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRB = os.path.join(ROOT, "data", "bible", "drb")

_VERSES: dict[str, dict] | None = None


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

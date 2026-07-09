"""
Locks the Douay-Rheims Bible ingest and verse-text resolution.
Run: python tests/test_bible.py   (ingest first: python ingest/bible.py)
"""

import glob
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "ingest"))
sys.path.insert(0, os.path.join(ROOT, "demo"))
from bible import extract_chapter, normalize_numbering, book_for  # noqa: E402
from scripture import normalize_ref  # noqa: E402
from bible_text import verses_for, load_verses  # noqa: E402

DRB = os.path.join(ROOT, "data", "bible", "drb")


def test_parser_units():
    # double-spaced chapter: wrapped lines (single blank) join; footnotes and the
    # chapter summary (paragraph-separated) are excluded; a verse with NO space after
    # the period is still captured (the 7-verse silent-drop bug this guards against).
    chunk = (
        "God createth all things.\n\n\n"
        "1:1. In the beginning God created heaven,\n\nand earth.\n\n\n"
        "A note.... this is Challoner's footnote, not scripture, and\n\nmust be dropped.\n\n\n"
        "1:2.No space after the period here.\n"
    )
    verses = extract_chapter(chunk, 1)
    assert verses == [(1, "In the beginning God created heaven, and earth."),
                      (2, "No space after the period here.")], verses


def test_numbering_normalization():
    # a Vulgate psalm restart continues numbering (part 2 verse 1 -> running max + 1)
    raw = [(1, "a"), (2, "b"), (1, "c"), (2, "d")]
    assert normalize_numbering("psalms", 113, raw) == [(1, "a"), (2, "b"), (3, "c"), (4, "d")]
    # a genuine duplicate label merges text under the one verse
    raw = [(11, "x"), (12, "first"), (12, "second"), (13, "y")]
    assert normalize_numbering("proverbs", 12, raw) == [(11, "x"), (12, "first second"), (13, "y")]


def test_douay_naming():
    # the Douay historical-book collisions map to the modern slug the Summa cites
    assert book_for("1 Kings") == ("1 Samuel", "1-samuel")
    assert book_for("3 Kings") == ("1 Kings", "1-kings")
    assert book_for("1 Esdras") == ("Ezra", "ezra")
    assert book_for("Apocalypse") == ("Revelation", "revelation")
    assert book_for("Ecclesiasticus") == ("Sirach", "sirach")


def test_corpus_completeness():
    files = glob.glob(os.path.join(DRB, "*.jsonl"))
    assert len(files) == 73, len(files)
    v = load_verses()
    assert len(v) >= 35000, len(v)
    # every id is unique and matches its verse_key
    assert len(v) == len({vk for vk in v})


def test_verse_resolution():
    # John 1:14 resolves to the full verbatim verse (not truncated at the first wrap)
    d = verses_for(normalize_ref("John 1:14"))
    assert len(d) == 1
    assert d[0]["text"].startswith("And the Word was made flesh")
    assert d[0]["text"].rstrip().endswith("full of grace and truth."), d[0]["text"][-40:]

    # a Douay "1 Kings" verse is addressable as the modern 1 Samuel citation
    d = verses_for(normalize_ref("1 Samuel 2:2"))
    assert d and d[0]["text"].startswith("There is none holy as the Lord")

    # the Vulgate-continuous Psalm 113:24 exists (the Summa cites it; the restart was
    # renumbered so it resolves)
    d = verses_for(normalize_ref("Psalm 113:24"))
    assert d and "heaven of heaven" in d[0]["text"]

    # a range returns each verse in order
    d = verses_for(normalize_ref("Genesis 1:1-3"))
    assert [x["verse"] for x in d] == [1, 2, 3]

    # a chapter reference returns the whole chapter
    d = verses_for(normalize_ref("Jude 1"))
    assert len(d) == 25, len(d)


if __name__ == "__main__":
    test_parser_units()
    test_numbering_normalization()
    test_douay_naming()
    test_corpus_completeness()
    test_verse_resolution()
    print("OK: parser drops nothing, Douay names + Vulgate numbering resolve, "
          "verses are verbatim and addressable")

"""
Locks the Clementine Vulgate ingest and parallel Latin verse resolution.
Run: python tests/test_vulgate.py   (ingest first: python ingest/vulgate.py)
"""

import glob
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "ingest"))
sys.path.insert(0, os.path.join(ROOT, "demo"))
from vulgate import clean_latin, BOOKS, ALLOWED_NONASCII  # noqa: E402
from scripture import normalize_ref  # noqa: E402
from bible_text import latin_for, load_latin, verses_for  # noqa: E402

VG = os.path.join(ROOT, "data", "bible", "vg")


def test_cleaner_strips_markup_only():
    # poetic line breaks '/', paragraph mark '\\', and poetic brackets '[ ]' become
    # whitespace and collapse; the Latin words (and ligatures) are untouched.
    raw = "[Et Verbum caro factum est,/ et habitavit in nobis :/ plenum gratiæ et veritatis.]\\"
    assert clean_latin(raw) == "Et Verbum caro factum est, et habitavit in nobis : plenum gratiæ et veritatis."
    # a marginal speaker rubric (Canticle) is editorial apparatus - dropped WHOLE, not
    # left as a stray word.
    assert clean_latin("<Sponsa>Osculetur me osculo oris sui ;/ quia meliora sunt ubera tua vino,") \
        == "Osculetur me osculo oris sui ; quia meliora sunt ubera tua vino,"
    # a marker can only ever separate words, never join two into one
    assert clean_latin("verbum/aliud") == "verbum aliud"


def test_book_map_covers_the_canon():
    slugs = {slug for _abbr, (slug, _lat) in BOOKS.items()}
    assert len(BOOKS) == 73, len(BOOKS)
    assert len(slugs) == 73, "duplicate slug in BOOKS"
    # the tricky Vulgate abbreviations land on the modern slug the Summa cites
    assert BOOKS["3Rg"][0] == "1-kings"      # Regum III = 1 Kings
    assert BOOKS["1Rg"][0] == "1-samuel"     # Regum I = 1 Samuel
    assert BOOKS["Esr"][0] == "ezra"         # Esdrae = Ezra
    assert BOOKS["Apc"][0] == "revelation"   # Apocalypsis
    assert BOOKS["Sir"][0] == "sirach"       # Ecclesiasticus


def test_corpus_shape_and_encoding():
    files = glob.glob(os.path.join(VG, "*.jsonl"))
    assert len(files) == 73, len(files)
    la = load_latin()
    assert len(la) >= 35000, len(la)
    # every stored Latin verse: no leaked markup, only the allowed non-ASCII ligatures
    for k, d in la.items():
        t = d["text"]
        assert not any(c in t for c in "/\\[]<>"), (k, t[:40])
        for c in t:
            assert ord(c) < 128 or c in ALLOWED_NONASCII, (k, hex(ord(c)))


def test_latin_resolution_and_parallel():
    # John 1:14 resolves to the verbatim Clementine Latin, keyed identically to Douay
    la = latin_for(normalize_ref("John 1:14"))
    assert la.get("john/1/14", "").startswith("Et Verbum caro factum est")
    assert la["john/1/14"].endswith("plenum gratiæ et veritatis.")

    # the same reference resolves to English AND Latin, verse-for-verse (parallel text)
    norm = normalize_ref("Genesis 1:1-3")
    en = verses_for(norm)
    lat = latin_for(norm)
    assert [x["verse"] for x in en] == [1, 2, 3]
    for d in en:
        assert f"genesis/1/{d['verse']}" in lat, "English verse lacks its Latin parallel"
    assert lat["genesis/1/1"].startswith("In principio creavit Deus")

    # a whole chapter returns the chapter's Latin
    chap = latin_for(normalize_ref("Jude 1"))
    assert len(chap) == 25, len(chap)


def test_vulgate_out_of_corpus_is_empty_not_wrong():
    # a reference with no verse address returns nothing rather than a wrong verse
    assert latin_for(normalize_ref("Genesis 999:1")) == {}


if __name__ == "__main__":
    test_cleaner_strips_markup_only()
    test_book_map_covers_the_canon()
    test_corpus_shape_and_encoding()
    test_latin_resolution_and_parallel()
    test_vulgate_out_of_corpus_is_empty_not_wrong()
    print("OK: cleaner strips only markup, canon maps, Latin resolves verbatim and "
          "parallels the Douay verse-for-verse")

"""
Scripture reference normalization.

Turns a raw citation as it appears in the Summa ("2 Timothy 3:16", "Psalm 90:15-16",
"Sirach 24:29") into a canonical, addressable form so citations become graph edges:

    {book, slug, chapter, verse_start, verse_end, ref, verse_keys, chapter_key}

Uses the Catholic (Douay-Rheims) canon with common modern/Douay name variants. A
reference whose book we do not recognize returns None and is counted as unparsed -
we never silently drop or guess.
"""

from __future__ import annotations

import re

# (canonical display name, slug, [variant keys]). Variant keys are matched after
# lowercasing and stripping spaces/periods. Covers modern and Douay-Rheims names.
_BOOKS_RAW = [
    ("Genesis", "genesis", ["gen"]),
    ("Exodus", "exodus", ["ex", "exod"]),
    ("Leviticus", "leviticus", ["lev"]),
    ("Numbers", "numbers", ["num"]),
    ("Deuteronomy", "deuteronomy", ["deut"]),
    ("Joshua", "joshua", ["josue", "jos"]),
    ("Judges", "judges", ["judg"]),
    ("Ruth", "ruth", []),
    ("1 Samuel", "1-samuel", ["1samuel", "1kings", "1kgs", "1sam", "1k"]),
    ("2 Samuel", "2-samuel", ["2samuel", "2kings", "2sam", "2k"]),
    ("1 Kings", "1-kings", ["3kings", "3k"]),
    ("2 Kings", "2-kings", ["4kings", "4k"]),
    ("1 Chronicles", "1-chronicles", ["1paralipomenon", "1par", "1chron"]),
    ("2 Chronicles", "2-chronicles", ["2paralipomenon", "2par", "2chron"]),
    ("Ezra", "ezra", ["1esdras", "1esd"]),
    ("Nehemiah", "nehemiah", ["2esdras", "2esd", "neh"]),
    ("Tobit", "tobit", ["tobias", "tob"]),
    ("Judith", "judith", ["jdt"]),
    ("Esther", "esther", ["esth"]),
    ("Job", "job", []),
    ("Psalm", "psalms", ["psalms", "ps", "psa"]),
    ("Proverbs", "proverbs", ["prov", "prv"]),
    ("Ecclesiastes", "ecclesiastes", ["eccles", "qoheleth", "eccl"]),
    ("Song of Songs", "song-of-songs", ["canticleofcanticles", "canticles", "canticle", "songofsolomon", "song"]),
    ("Wisdom", "wisdom", ["wis"]),
    ("Sirach", "sirach", ["ecclesiasticus", "sir", "ecclus"]),
    ("Isaiah", "isaiah", ["isaias", "isa", "is"]),
    ("Jeremiah", "jeremiah", ["jeremias", "jer"]),
    ("Lamentations", "lamentations", ["lam"]),
    ("Baruch", "baruch", ["bar"]),
    ("Ezekiel", "ezekiel", ["ezechiel", "ezek", "eze"]),
    ("Daniel", "daniel", ["dan"]),
    ("Hosea", "hosea", ["osee", "hos"]),
    ("Joel", "joel", []),
    ("Amos", "amos", []),
    ("Obadiah", "obadiah", ["abdias", "obad"]),
    ("Jonah", "jonah", ["jonas", "jon"]),
    ("Micah", "micah", ["micheas", "mic"]),
    ("Nahum", "nahum", ["nah"]),
    ("Habakkuk", "habakkuk", ["habacuc", "hab"]),
    ("Zephaniah", "zephaniah", ["sophonias", "zeph"]),
    ("Haggai", "haggai", ["aggeus", "hag"]),
    ("Zechariah", "zechariah", ["zacharias", "zech"]),
    ("Malachi", "malachi", ["malachias", "mal"]),
    ("1 Maccabees", "1-maccabees", ["1machabees", "1mac", "1macc"]),
    ("2 Maccabees", "2-maccabees", ["2machabees", "2mac", "2macc"]),
    ("Matthew", "matthew", ["matt", "mt"]),
    ("Mark", "mark", ["mk", "mrk"]),
    ("Luke", "luke", ["lk", "luk"]),
    ("John", "john", ["jn", "joh"]),
    ("Acts", "acts", ["actsoftheapostles", "act"]),
    ("Romans", "romans", ["rom"]),
    ("1 Corinthians", "1-corinthians", ["1corinthians", "1cor", "1co"]),
    ("2 Corinthians", "2-corinthians", ["2corinthians", "2cor", "2co"]),
    ("Galatians", "galatians", ["gal"]),
    ("Ephesians", "ephesians", ["eph"]),
    ("Philippians", "philippians", ["phil", "php"]),
    ("Colossians", "colossians", ["col"]),
    ("1 Thessalonians", "1-thessalonians", ["1thessalonians", "1thess", "1th"]),
    ("2 Thessalonians", "2-thessalonians", ["2thessalonians", "2thess", "2th"]),
    ("1 Timothy", "1-timothy", ["1timothy", "1tim", "1ti"]),
    ("2 Timothy", "2-timothy", ["2timothy", "2tim", "2ti"]),
    ("Titus", "titus", ["tit"]),
    ("Philemon", "philemon", ["philem", "phlm"]),
    ("Hebrews", "hebrews", ["heb"]),
    ("James", "james", ["jas", "jam"]),
    ("1 Peter", "1-peter", ["1peter", "1pet", "1pt"]),
    ("2 Peter", "2-peter", ["2peter", "2pet", "2pt"]),
    ("1 John", "1-john", ["1john", "1jn", "1jo"]),
    ("2 John", "2-john", ["2john", "2jn"]),
    ("3 John", "3-john", ["3john", "3jn"]),
    ("Jude", "jude", []),
    ("Revelation", "revelation", ["apocalypse", "apoc", "rev"]),
]


def _key(s: str) -> str:
    return re.sub(r"[\s.]", "", s.lower())


_BOOK_LOOKUP: dict[str, tuple[str, str]] = {}
for _name, _slug, _variants in _BOOKS_RAW:
    _BOOK_LOOKUP[_key(_name)] = (_name, _slug)
    _BOOK_LOOKUP[_slug.replace("-", "")] = (_name, _slug)
    for _v in _variants:
        _BOOK_LOOKUP[_key(_v)] = (_name, _slug)


def resolve_book(name: str) -> tuple[str, str] | None:
    """Map a book name (modern OR Douay-Rheims, e.g. 'Osee', '1 Kings',
    'Ecclesiasticus', 'Apocalypse') to (canonical display name, slug), or None if
    unrecognized. Single source of truth for the slug map, so Bible ingest and
    citation normalization key verses identically."""
    return _BOOK_LOOKUP.get(_key(name))

_REF = re.compile(
    r"^\s*([1-4]?\s?[A-Za-z][A-Za-z.'\s]*?)\s+(\d+)(?::(\d+)(?:\s*[-–]\s*(\d+))?)?\s*$"
)


def normalize_ref(raw: str) -> dict | None:
    # "Romans 5:15, seqq." means that verse and the following ones; keep the
    # anchor verse (an open range we do not try to bound).
    raw = re.sub(r",?\s*(seqq?|sqq)\.?\s*$", "", raw, flags=re.I)
    m = _REF.match(raw)
    if not m:
        return None
    book_raw, ch, v1, v2 = m.groups()
    canon = _BOOK_LOOKUP.get(_key(book_raw))
    if not canon:
        return None
    book, slug = canon
    chapter = int(ch)

    if v1 is None:  # book + chapter only
        return {
            "book": book, "slug": slug, "chapter": chapter,
            "verse_start": None, "verse_end": None,
            "ref": f"{book} {chapter}",
            "verse_keys": [f"{slug}/{chapter}"],
            "chapter_key": f"{slug}/{chapter}",
        }

    vs = int(v1)
    ve = int(v2) if v2 else vs
    if ve < vs:
        ve = vs
    ref = f"{book} {chapter}:{vs}" + (f"-{ve}" if ve != vs else "")
    return {
        "book": book, "slug": slug, "chapter": chapter,
        "verse_start": vs, "verse_end": ve,
        "ref": ref,
        "verse_keys": [f"{slug}/{chapter}/{x}" for x in range(vs, ve + 1)],
        "chapter_key": f"{slug}/{chapter}",
    }

"""
Build the date -> Mass Gospel table that powers "the Fathers on today's Gospel".

We take only the GOSPEL REFERENCE for each day (a fact, freely usable) and the English
liturgical day name; the verse text itself we already hold verbatim in the public-domain
Douay-Rheims, and the Fathers come from our Catena Aurea. Two sources, joined by date, so
no movable-feast calendar has to be computed here:

  - the Gospel reference   <- AELF (api.aelf.org), the universal Ordinary-Form lectionary
  - the English day name    <- inadiutorium (calapi.inadiutorium.cz), General Roman Calendar

Only the reference and the day name are stored; no third-party reading text is copied.
Stdlib only. Run:  python ingest/lectionary.py [START] [END]   (YYYY-MM-DD, inclusive)
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from scripture import normalize_ref  # noqa: E402

OUT_DIR = os.path.join(ROOT, "data", "lectionary")
FR_GOSPEL = {"Mt": "Matthew", "Mc": "Mark", "Lc": "Luke", "Jn": "John"}
GOSPEL_SLUGS = {"matthew", "mark", "luke", "john"}
# whitespace/dash variants AELF uses in references, normalized away by unicode escape
_WS = [chr(0xA0), chr(0x202F), chr(0x2009), chr(0x2007)]  # nbsp, narrow-nbsp, thin, figure space
_DASHES = [chr(0x2011), chr(0x2012), chr(0x2013), chr(0x2014), chr(0x2212)]  # nb-hyphen, figure, en, em, minus


def _get(url: str, tries: int = 3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "catena-lectionary/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if i == tries - 1:
                return None
            time.sleep(1.0 + i)
    return None


def norm_gospel(ref: str) -> str | None:
    """French AELF ref -> our 'Book Ch:Vv' form. 'Mt 10, 16-23' -> 'Matthew 10:16-23';
    'Jn 6, 51.53-58' -> 'John 6:51,53-58'; 'Mt 26, 14-27, 66' -> 'Matthew 26:14-27:66'."""
    if not ref:
        return None
    for w in _WS:
        ref = ref.replace(w, " ")
    for d in _DASHES:
        ref = ref.replace(d, "-")
    ref = ref.strip()
    for full, ab in (("Matthieu", "Mt"), ("Marc", "Mc"), ("Luc", "Lc"), ("Jean", "Jn")):
        ref = re.sub(rf"\b{full}\b", ab, ref)
    # the book+chapter may sit after a prefix ("Stabat Mater. Jn 19, 25-27"); search, don't anchor
    m = re.search(r"\b(Mt|Mc|Lc|Jn)\s+(\d.*)$", ref)
    if not m:
        return None
    book = FR_GOSPEL[m.group(1)]
    body = re.sub(r"(\d+)\s*,\s*", r"\1:", m.group(2))   # chapter comma -> colon
    body = body.replace(".", ",")                          # non-contiguous verses . -> ,
    body = re.sub(r"\s+", "", body)
    return f"{book} {body}"


def gospel_from_aelf(date: str):
    d = _get(f"https://api.aelf.org/v1/messes/{date}/romain")
    if not d:
        return None
    masses = d.get("messes") or []
    # prefer the day Mass (skip a vigil) but accept whatever carries a Gospel
    masses = sorted(masses, key=lambda m: 0 if "jour" in (m.get("nom") or "").lower() else 1)
    for mass in masses:
        for lec in mass.get("lectures", []):
            if lec.get("type") == "evangile":
                return lec.get("ref")
    return None


def day_name(y: int, mo: int, dy: int):
    d = _get(f"http://calapi.inadiutorium.cz/api/v0/en/calendars/general-en/{y}/{mo}/{dy}")
    if not d:
        return None
    cels = d.get("celebrations") or []
    return cels[0].get("title") if cels else None


def _verse_keys_single_chapter(canonical_ref: str):
    """Return (slug, verse_keys) if the ref is single-chapter and in a Gospel, else key=None."""
    norm = normalize_ref(canonical_ref)
    if not norm:
        return None, None
    slug = norm.get("slug")
    if slug not in GOSPEL_SLUGS:
        return slug, None
    return slug, norm.get("verse_keys")


def main():
    start = sys.argv[1] if len(sys.argv) > 1 else _dt.date.today().isoformat()
    end = sys.argv[2] if len(sys.argv) > 2 else (_dt.date.fromisoformat(start) + _dt.timedelta(days=175)).isoformat()
    d0, d1 = _dt.date.fromisoformat(start), _dt.date.fromisoformat(end)

    # gospel verses we actually hold, for reference validation
    drb = set()
    for slug in GOSPEL_SLUGS:
        p = os.path.join(ROOT, "data", "bible", "drb", f"{slug}.jsonl")
        for line in open(p, encoding="utf-8"):
            drb.add(json.loads(line)["verse_key"])

    outpath = os.path.join(OUT_DIR, "gospels.json")
    out = json.load(open(outpath, encoding="utf-8")) if os.path.exists(outpath) else {}
    unparsed, cross_chapter, missing_verses = [], [], []
    day = d0
    while day <= d1:
        iso = day.isoformat()
        if out.get(iso, {}).get("gospel"):     # resume: keep days already fetched
            day += _dt.timedelta(days=1)
            continue
        raw = gospel_from_aelf(iso)
        ref = norm_gospel(raw) if raw else None
        if not ref:
            unparsed.append((iso, raw))
            day += _dt.timedelta(days=1)
            continue
        slug, vkeys = _verse_keys_single_chapter(ref)
        entry = {"gospel": ref}
        nm = day_name(day.year, day.month, day.day)
        if nm:
            entry["day"] = nm
        out[iso] = entry
        if vkeys is None:
            cross_chapter.append((iso, ref))     # multi-chapter passion etc: shown, partially resolved
        else:
            missing = [k for k in vkeys if k not in drb]
            if missing:
                missing_verses.append((iso, ref, missing[:3]))
        time.sleep(0.12)
        day += _dt.timedelta(days=1)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "gospels.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0, sort_keys=True)

    print(f"wrote data/lectionary/gospels.json  {len(out)} days  ({start} .. {end})")
    print(f"  single-chapter refs validated against Douay-Rheims: "
          f"{len(out) - len(cross_chapter)}  cross-chapter (partial resolve): {len(cross_chapter)}")
    print(f"  unparsed gospel refs: {len(unparsed)}  refs with a verse missing from DRB: {len(missing_verses)}")
    for iso, raw in unparsed[:8]:
        print(f"    UNPARSED {iso}: {raw!r}")
    for iso, ref, miss in missing_verses[:8]:
        print(f"    VERSE-GAP {iso}: {ref} -> {miss}")


if __name__ == "__main__":
    main()

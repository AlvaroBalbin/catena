"""
Independent validation of the ingested corpus.

Re-checks the schema invariants against the written .jsonl files (not trusting the
ingest run), so `python ingest/validate.py` is a standalone integrity gate:

Summa:
  1. every node has a unique id, non-empty text, and a source with a license
  2. segments rejoin to text exactly (lossless)
  3. the canonical citation parses back to the node's structural position
  4. per-part question coverage has no gaps (completeness)

Douay-Rheims Bible (if ingested):
  1. every verse node has a unique id, non-empty text, and a source with a license
  2. id, citation, and verse_key agree with the node's book/chapter/verse
  3. every book present with its known chapter count; verses unique and contiguous
     (completeness), starting at verse 1 save the documented Vulgate psalm splits
  4. every verse's text appears verbatim in the raw source (lossless), when the source
     cache is present

Clementine Vulgate (if ingested):
  1. every verse node has a unique id, non-empty Latin text (lang la), a license, and
     no leaked markup or unexpected non-ASCII beyond the edition's Latin ligatures
  2. id, citation, and verse_key agree with the node's book/chapter/verse
  3. every book present with its known chapter count; verses unique and contiguous
  4. every verse re-derives exactly from the raw source under the documented cleaner
     (lossless), when the per-book source cache is present
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SUMMA = os.path.join(ROOT, "data", "summa")
CATENA = os.path.join(ROOT, "data", "catena")
CATECHISM = os.path.join(ROOT, "data", "catechism")
BIBLE = os.path.join(ROOT, "data", "bible", "drb")
VULGATE = os.path.join(ROOT, "data", "bible", "vg")

CIT = re.compile(r"^ST (I|I-II|II-II|III|Suppl\.), q\.(\d+), a\.(\d+)$")
ID = re.compile(r"^summa\.st\.(i|i-ii|ii-ii|iii|suppl)\.q(\d+)\.a(\d+)$")

# Catena: id -> (slug, chapter, start-verse); citation -> (book, chapter, verses)
CATENA_GOSPELS = {"matthew": "Matthew", "mark": "Mark", "luke": "Luke", "john": "John"}
CATENA_CHAPTERS = {"matthew": 28, "mark": 16, "luke": 24, "john": 21}
CAT_ID = re.compile(r"^catena\.(matthew|mark|luke|john)\.(\d+)\.(\d+)$")
CAT_CIT = re.compile(r"^Catena Aurea, (Matthew|Mark|Luke|John) (\d+):(\d+)(?:-(\d+))?$")

# Roman Catechism: id -> (part, unit code, subsection); citation carries Part + unit.
CATECHISM_ID = re.compile(r"^catechism\.p([1-4])\.([a-z0-9-]+)\.s(\d{2,})$")
CATECHISM_CIT = re.compile(r"^Roman Catechism, Part (I|II|III|IV), .+ : .+$", re.S)
CATECHISM_ROMAN = {"1": "I", "2": "II", "3": "III", "4": "IV"}


def fail(msg: str) -> None:
    print("FAIL:", msg)
    sys.exit(1)


def validate_summa() -> None:
    files = sorted(glob.glob(os.path.join(SUMMA, "summa-*.jsonl")))
    if not files:
        fail("no Summa corpus files found; run ingest first")

    ids: set[str] = set()
    total = 0
    coverage: dict[str, set[int]] = {}

    for path in files:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            node = json.loads(line)
            total += 1
            nid = node["id"]

            if nid in ids:
                fail(f"duplicate id {nid}")
            ids.add(nid)

            if not node.get("text", "").strip():
                fail(f"empty text: {nid}")

            src = node.get("source") or {}
            if not src.get("license"):
                fail(f"missing license: {nid}")

            rejoin = "\n\n".join(s["text"] for s in node["segments"])
            if rejoin != node["text"]:
                fail(f"lossless invariant broken: {nid}")

            cm = CIT.match(node["citation"])
            if not cm:
                fail(f"unparseable citation {node['citation']!r} on {nid}")
            im = ID.match(nid)
            if not im:
                fail(f"unparseable id {nid}")
            if (im.group(2), im.group(3)) != (cm.group(2), cm.group(3)):
                fail(f"id/citation mismatch: {nid} vs {node['citation']}")

            part = im.group(1)
            coverage.setdefault(part, set()).add(int(im.group(2)))

    expected = {"i": 119, "i-ii": 114, "ii-ii": 189, "iii": 90, "suppl": 99}
    for part, qs in coverage.items():
        gaps = set(range(1, expected[part] + 1)) - qs
        if gaps:
            fail(f"part {part}: missing questions {sorted(gaps)[:15]}")

    print(f"Summa OK: {total} nodes, {len(ids)} unique ids")
    print("  parts covered:", {p: len(q) for p, q in sorted(coverage.items())})


def validate_bible() -> None:
    files = sorted(glob.glob(os.path.join(BIBLE, "*.jsonl")))
    if not files:
        print("Bible: not ingested (skipped)")
        return

    # imported here so the Summa gate still runs even if the Bible module changes
    from bible import EXPECTED_CHAPTERS, KNOWN_VERSE_START, iter_chapters, \
        strip_gutenberg, _collapse, CACHE  # noqa

    ids: set[str] = set()
    by_book: dict[str, dict[int, list[int]]] = {}
    by_key: dict[str, str] = {}   # verse_key -> collapsed text, for the lossless check
    total = 0

    for path in files:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            n = json.loads(line)
            total += 1
            nid = n["id"]
            if nid in ids:
                fail(f"duplicate id {nid}")
            ids.add(nid)

            if n.get("type") != "verse":
                fail(f"non-verse node in Bible: {nid}")
            if not n.get("text", "").strip():
                fail(f"empty verse text: {nid}")
            src = n.get("source") or {}
            if not src.get("license"):
                fail(f"missing license: {nid}")

            slug = n["verse_key"].split("/")[0]
            ch, v = n["chapter"], n["verse"]
            if nid != f"drb.{slug}.{ch}.{v}":
                fail(f"id/position mismatch: {nid}")
            if n["verse_key"] != f"{slug}/{ch}/{v}":
                fail(f"verse_key mismatch: {nid}")
            if n["citation"] != f"{n['book']} {ch}:{v}":
                fail(f"citation mismatch: {nid} vs {n['citation']}")

            by_book.setdefault(slug, {}).setdefault(ch, []).append(v)
            by_key[n["verse_key"]] = n["text"]

    # completeness
    for slug in EXPECTED_CHAPTERS:
        if slug not in by_book:
            fail(f"missing book: {slug}")
    for slug in by_book:
        if slug not in EXPECTED_CHAPTERS:
            fail(f"unexpected book: {slug}")
    for slug, expected in EXPECTED_CHAPTERS.items():
        chapters = by_book[slug]
        if max(chapters) != expected:
            fail(f"{slug}: {max(chapters)} chapters, expected {expected}")
        for ch in range(1, expected + 1):
            vs = sorted(chapters.get(ch, []))
            if not vs:
                fail(f"{slug} ch.{ch}: no verses")
            if len(vs) != len(set(vs)):
                fail(f"{slug} ch.{ch}: duplicate verse numbers")
            start = KNOWN_VERSE_START.get((slug, ch), 1)
            if vs[0] != start or vs != list(range(vs[0], vs[-1] + 1)):
                fail(f"{slug} ch.{ch}: non-contiguous verses {vs[:5]}..{vs[-3:]}")

    # lossless: every verse text appears verbatim in the raw source (marker-stripped,
    # whitespace-collapsed). Independent of the ingest run; needs the source cache.
    src_path = os.path.join(CACHE, "pg1581.txt")
    if os.path.exists(src_path):
        raw = open(src_path, encoding="utf-8", errors="replace").read()
        body = strip_gutenberg(raw)
        # bucket verses by (slug, chapter) so each chapter is scanned once
        buckets: dict[tuple[str, int], list[tuple[str, str]]] = {}
        for key, text in by_key.items():
            ks, kc, _kv = key.split("/")
            buckets.setdefault((ks, int(kc)), []).append((key, text))
        checked = 0
        for _db, _canon, slug, ch, chunk in iter_chapters(body):
            flat = _collapse(re.sub(r"\d+:\d+\.\s*", "", chunk))
            for key, text in buckets.get((slug, ch), []):
                if text not in flat:
                    fail(f"lossless: verse {key} text not found verbatim in source")
                checked += 1
        print(f"Bible OK: {total} verses, {len(by_book)} books; "
              f"lossless verified against source for {checked} verses")
    else:
        print(f"Bible OK: {total} verses, {len(by_book)} books "
              "(lossless-vs-source skipped: source cache absent)")


def validate_vulgate() -> None:
    files = sorted(glob.glob(os.path.join(VULGATE, "*.jsonl")))
    if not files:
        print("Clementine Vulgate: not ingested (skipped)")
        return

    # imported here so the earlier gates still run even if the Vulgate module changes
    from vulgate import (EXPECTED_CHAPTERS, BOOKS, ALLOWED_NONASCII, clean_latin,
                         CACHE as VG_CACHE, _VERSE as VG_LINE)  # noqa
    slug_to_abbr = {slug: abbr for abbr, (slug, _lat) in BOOKS.items()}

    ids: set[str] = set()
    by_book: dict[str, dict[int, list[int]]] = {}
    by_key: dict[str, str] = {}   # verse_key -> stored Latin, for the lossless check
    total = 0

    for path in files:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            n = json.loads(line)
            total += 1
            nid = n["id"]
            if nid in ids:
                fail(f"duplicate id {nid}")
            ids.add(nid)

            if n.get("type") != "verse":
                fail(f"non-verse node in Vulgate: {nid}")
            if n.get("lang") != "la":
                fail(f"non-Latin lang on Vulgate node: {nid}")
            if not n.get("text", "").strip():
                fail(f"empty verse text: {nid}")
            src = n.get("source") or {}
            if not src.get("license"):
                fail(f"missing license: {nid}")

            # no markup leaked; only the allowed Latin ligatures beyond ASCII
            if any(c in n["text"] for c in "/\\[]<>"):
                fail(f"markup leaked into Latin text: {nid}")
            for c in n["text"]:
                if ord(c) > 127 and c not in ALLOWED_NONASCII:
                    fail(f"unexpected non-ASCII {c!r} (U+{ord(c):04X}) in {nid}")

            slug = n["verse_key"].split("/")[0]
            ch, v = n["chapter"], n["verse"]
            if nid != f"vg.{slug}.{ch}.{v}":
                fail(f"id/position mismatch: {nid}")
            if n["verse_key"] != f"{slug}/{ch}/{v}":
                fail(f"verse_key mismatch: {nid}")
            if n["citation"] != f"{n['book']} {ch}:{v}":
                fail(f"citation mismatch: {nid} vs {n['citation']}")

            by_book.setdefault(slug, {}).setdefault(ch, []).append(v)
            by_key[n["verse_key"]] = n["text"]

    # completeness against the shared canon spec
    for slug in EXPECTED_CHAPTERS:
        if slug not in by_book:
            fail(f"missing book: {slug}")
    for slug in by_book:
        if slug not in EXPECTED_CHAPTERS:
            fail(f"unexpected book: {slug}")
    for slug, expected in EXPECTED_CHAPTERS.items():
        chapters = by_book[slug]
        if max(chapters) != expected:
            fail(f"{slug}: {max(chapters)} chapters, expected {expected}")
        for ch in range(1, expected + 1):
            vs = sorted(chapters.get(ch, []))
            if not vs:
                fail(f"{slug} ch.{ch}: no verses")
            if len(vs) != len(set(vs)):
                fail(f"{slug} ch.{ch}: duplicate verse numbers")
            if vs[0] != 1 or vs != list(range(vs[0], vs[-1] + 1)):
                fail(f"{slug} ch.{ch}: non-contiguous verses {vs[:5]}..{vs[-3:]}")

    # lossless: re-parse the raw source cache with the SAME cleaner and require an
    # exact match. Independent of the ingest run; proves the transform is the only
    # thing between source and stored text. Needs the per-book source cache.
    if os.path.isdir(VG_CACHE) and glob.glob(os.path.join(VG_CACHE, "*.lat")):
        checked = 0
        for slug, chapters in by_book.items():
            abbr = slug_to_abbr[slug]
            src = os.path.join(VG_CACHE, f"{abbr}.lat")
            if not os.path.exists(src):
                fail(f"source cache missing for {slug} ({abbr}.lat)")
            raw = open(src, "rb").read().decode("cp1252")
            src_by_key: dict[str, str] = {}
            for ln in raw.splitlines():
                m = VG_LINE.match(ln.rstrip())
                if m:
                    src_by_key[f"{slug}/{int(m.group(1))}/{int(m.group(2))}"] = clean_latin(m.group(3))
            for ch, vs in chapters.items():
                for v in vs:
                    k = f"{slug}/{ch}/{v}"
                    if by_key[k] != src_by_key.get(k):
                        fail(f"lossless: verse {k} does not match source under the cleaner")
                    checked += 1
        print(f"Vulgate OK: {total} verses, {len(by_book)} books; "
              f"lossless re-derived from source for {checked} verses")
    else:
        print(f"Vulgate OK: {total} verses, {len(by_book)} books "
              "(lossless-vs-source skipped: source cache absent)")


def validate_catena() -> None:
    files = sorted(glob.glob(os.path.join(CATENA, "*.jsonl")))
    if not files:
        print("Catena Aurea: not ingested (skipped)")
        return

    # golden-chain join target: every commented verse must be a real DRB verse.
    drb_files = sorted(glob.glob(os.path.join(BIBLE, "*.jsonl")))
    if not drb_files:
        fail("Catena join-key check needs the Douay-Rheims Bible; ingest it first")
    drb_keys: set[str] = set()
    for path in drb_files:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                drb_keys.add(json.loads(line)["verse_key"])

    ids: set[str] = set()
    total = 0
    frags = 0
    by_gospel: dict[str, set[int]] = {}

    for path in files:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            n = json.loads(line)
            total += 1
            nid = n["id"]

            if nid in ids:
                fail(f"duplicate id {nid}")
            ids.add(nid)

            if n.get("type") != "father-comment":
                fail(f"unexpected type {n.get('type')!r} on {nid}")
            if not n.get("text", "").strip():
                fail(f"empty text: {nid}")

            src = n.get("source") or {}
            if not src.get("license"):
                fail(f"missing license: {nid}")

            # lossless: segments rejoin to text exactly
            segs = n.get("segments", [])
            if not segs:
                fail(f"no segments: {nid}")
            frags += len(segs)
            if "\n\n".join(s["text"] for s in segs) != n["text"]:
                fail(f"lossless invariant broken: {nid}")
            for s in segs:
                if not s.get("father"):
                    fail(f"segment without a Father on {nid}")

            # id <-> citation agreement
            im = CAT_ID.match(nid)
            if not im:
                fail(f"unparseable id {nid}")
            cm = CAT_CIT.match(n["citation"])
            if not cm:
                fail(f"unparseable citation {n['citation']!r} on {nid}")
            slug, ich, iv = im.group(1), im.group(2), im.group(3)
            if CATENA_GOSPELS[slug] != cm.group(1) or ich != cm.group(2) or iv != cm.group(3):
                fail(f"id/citation mismatch: {nid} vs {n['citation']}")

            # join-key integrity: every commented verse resolves in the DRB
            cvk = n.get("commented_verse_keys", [])
            if not cvk:
                fail(f"no commented_verse_keys: {nid}")
            for vk in cvk:
                if vk not in drb_keys:
                    fail(f"commented verse {vk} on {nid} is not a real DRB verse")
                if vk.split("/")[0] != slug:
                    fail(f"commented verse {vk} on {nid} is outside its gospel")

            by_gospel.setdefault(slug, set()).add(int(ich))

    # completeness: all four gospels, every chapter present, none empty
    for slug, expected in CATENA_CHAPTERS.items():
        if slug not in by_gospel:
            fail(f"missing gospel: {slug}")
        gaps = set(range(1, expected + 1)) - by_gospel[slug]
        if gaps:
            fail(f"{slug}: missing chapters {sorted(gaps)}")
    present_chapters = sum(len(v) for v in by_gospel.values())
    if present_chapters != sum(CATENA_CHAPTERS.values()):
        fail(f"expected {sum(CATENA_CHAPTERS.values())} chapters, saw {present_chapters}")

    print(f"Catena Aurea OK: {total} pericopes, {len(ids)} unique ids, {frags} fragments; "
          f"{present_chapters} chapters across {len(by_gospel)} gospels; "
          "segments rejoin to text and every commented verse resolves in the DRB")


def validate_catechism() -> None:
    files = sorted(glob.glob(os.path.join(CATECHISM, "part*.jsonl")))
    if not files:
        print("Roman Catechism: not ingested (skipped)")
        return

    # completeness targets: the numbered units that MUST be present per Part.
    EXPECTED = {"article": set(range(1, 13)), "sacrament": set(range(1, 8)),
                "commandment": set(range(1, 11)), "petition": set(range(1, 8))}
    # unit code -> (unit_type, [numbers]) so the id's code proves which unit is present.
    UNIT = {}
    for i in range(1, 13):
        UNIT[f"art{i}"] = ("article", [i])
    for i in range(1, 8):
        UNIT[f"pet{i}"] = ("petition", [i])
    for i, c in enumerate(["baptism", "confirmation", "eucharist", "penance",
                           "extreme-unction", "holy-orders", "matrimony"], start=1):
        UNIT[c] = ("sacrament", [i])
    for i in range(1, 9):
        UNIT[f"cmd{i}"] = ("commandment", [i])
    UNIT["cmd9-10"] = ("commandment", [9, 10])

    ids: set[str] = set()
    total = 0
    parts_seen: set[int] = set()
    present: dict[str, set[int]] = {k: set() for k in EXPECTED}

    for path in files:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            n = json.loads(line)
            total += 1
            nid = n["id"]

            if nid in ids:
                fail(f"duplicate id {nid}")
            ids.add(nid)

            if n.get("type") != "catechism":
                fail(f"unexpected type {n.get('type')!r} on {nid}")
            if not n.get("text", "").strip():
                fail(f"empty text: {nid}")

            src = n.get("source") or {}
            if not src.get("license"):
                fail(f"missing license: {nid}")

            # lossless: segments rejoin to text exactly
            segs = n.get("segments", [])
            if not segs:
                fail(f"no segments: {nid}")
            if "\n\n".join(s["text"] for s in segs) != n["text"]:
                fail(f"lossless invariant broken: {nid}")

            # id <-> citation agreement, and id encodes a known Part + unit
            im = CATECHISM_ID.match(nid)
            if not im:
                fail(f"unparseable id {nid}")
            if not CATECHISM_CIT.match(n["citation"]):
                fail(f"unparseable citation {n['citation']!r} on {nid}")
            part, code = im.group(1), im.group(2)
            if not n["citation"].startswith(f"Roman Catechism, Part {CATECHISM_ROMAN[part]},"):
                fail(f"id/citation Part mismatch: {nid} vs {n['citation']}")
            # title must appear at the end of the citation (canonical addressing)
            if n.get("title") and not n["citation"].rstrip().endswith(n["title"]):
                fail(f"citation does not end with the subsection title: {nid}")

            parts_seen.add(int(part))
            if code in UNIT:
                utype, nums = UNIT[code]
                present[utype].update(nums)

            # every citations_out scripture ref must parse via the shared normalizer
            for c in n.get("citations_out", []):
                if c.get("kind") == "scripture" and not normalize_ref(c["raw"]):
                    fail(f"unparseable scripture ref {c['raw']!r} on {nid}")

    # completeness: all four Parts, and every numbered unit within them
    if parts_seen != {1, 2, 3, 4}:
        fail(f"missing Parts: {sorted({1,2,3,4} - parts_seen)}")
    for utype, need in EXPECTED.items():
        missing = need - present[utype]
        if missing:
            fail(f"missing {utype}(s): {sorted(missing)}")

    print(f"Roman Catechism OK: {total} subsections, {len(ids)} unique ids; "
          "all four Parts, 12 Articles, 7 Sacraments, 10 Commandments, 7 Petitions; "
          "segments rejoin to text and every citation parses")


def main() -> None:
    validate_summa()
    validate_bible()
    validate_vulgate()
    validate_catena()
    validate_catechism()
    print("lossless, addressable, and complete for the ingested corpus.")


if __name__ == "__main__":
    main()

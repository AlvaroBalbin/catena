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
BIBLE = os.path.join(ROOT, "data", "bible", "drb")

CIT = re.compile(r"^ST (I|I-II|II-II|III|Suppl\.), q\.(\d+), a\.(\d+)$")
ID = re.compile(r"^summa\.st\.(i|i-ii|ii-ii|iii|suppl)\.q(\d+)\.a(\d+)$")


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


def main() -> None:
    validate_summa()
    validate_bible()
    print("lossless, addressable, and complete for the ingested corpus.")


if __name__ == "__main__":
    main()

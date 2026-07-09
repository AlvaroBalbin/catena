"""
Ingest the Summa Theologica from New Advent into data/summa/.

Politeness: identifies itself, caches every page locally (ingest/.cache/, gitignored)
so re-runs never refetch, and sleeps between live fetches. Resumable.

Output:
  data/summa/summa-<part_slug>.jsonl   one node (article) per line
  data/summa/manifest.json             counts + expected counts + provenance

Usage:
  python ingest/run.py --part 1          # ingest one part
  python ingest/run.py --all             # ingest all five parts
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from dataclasses import asdict

from summa import PARTS, parse_question_page

RETRIEVED = "2026-07-09"
UA = "Catena/0.1 (open Catholic corpus; contact via github.com/AlvaroBalbin/catena)"

# Known question counts per New Advent part page set. Used as the completeness
# check: every question 1..N must fetch and parse, or ingest fails loudly.
QUESTION_COUNTS = {1: 119, 2: 114, 3: 189, 4: 90, 5: 99}

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(HERE, ".cache")
OUT = os.path.join(ROOT, "data", "summa")


def fetch(part_num: int, q: int) -> str:
    """Fetch one question page, caching to disk. Returns HTML."""
    name = f"{part_num}{q:03d}.htm"
    cached = os.path.join(CACHE, name)
    if os.path.exists(cached):
        return open(cached, encoding="utf-8", errors="replace").read()
    url = f"https://www.newadvent.org/summa/{name}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="replace")
    os.makedirs(CACHE, exist_ok=True)
    with open(cached, "w", encoding="utf-8") as f:
        f.write(html)
    time.sleep(0.7)  # be a good guest
    return html


def ingest_part(part_num: int) -> dict:
    part_slug, part_disp, part_long = PARTS[part_num]
    n_questions = QUESTION_COUNTS[part_num]
    os.makedirs(OUT, exist_ok=True)
    out_path = os.path.join(OUT, f"summa-{part_slug}.jsonl")

    nodes_written = 0
    articles = 0
    missing = []
    with open(out_path, "w", encoding="utf-8") as out:
        for q in range(1, n_questions + 1):
            url = f"https://www.newadvent.org/summa/{part_num}{q:03d}.htm"
            html = fetch(part_num, q)
            try:
                nodes = parse_question_page(html, part_num, url, RETRIEVED)
            except Exception as e:  # a page that will not parse is a real gap
                missing.append((q, str(e)))
                continue
            if not nodes:
                missing.append((q, "no articles parsed"))
                continue
            for node in nodes:
                out.write(json.dumps(asdict(node), ensure_ascii=False) + "\n")
                nodes_written += 1
                articles += 1
            print(f"  {part_disp} q.{q}: {len(nodes)} articles")

    if missing:
        raise SystemExit(
            f"COMPLETENESS FAILURE in part {part_disp}: "
            f"{len(missing)} questions missing/unparsed: {missing[:10]}"
        )

    return {
        "part": part_disp,
        "slug": part_slug,
        "questions": n_questions,
        "articles": articles,
        "file": os.path.relpath(out_path, ROOT).replace("\\", "/"),
    }


def write_manifest(parts_done: list[dict]) -> None:
    manifest = {
        "work": "summa-theologiae",
        "title": "Summa Theologica",
        "author": "Thomas Aquinas",
        "edition": "Fathers of the English Dominican Province, 2nd rev. ed. (1920-22)",
        "license": "public-domain",
        "source": "https://www.newadvent.org/summa/",
        "retrieved": RETRIEVED,
        "structure": ["part", "question", "article"],
        "parts": parts_done,
        "totals": {
            "questions": sum(p["questions"] for p in parts_done),
            "articles": sum(p["articles"] for p in parts_done),
        },
    }
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("manifest:", manifest["totals"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", type=int, choices=[1, 2, 3, 4, 5])
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    parts = [1, 2, 3, 4, 5] if args.all else [args.part]
    if parts == [None]:
        ap.error("give --part N or --all")

    done = []
    for p in parts:
        print(f"== ingesting part {PARTS[p][1]} ==")
        done.append(ingest_part(p))
    # only (re)write manifest for a full run so it always reflects the whole corpus
    if args.all:
        write_manifest(done)
    else:
        print("part done:", done[0])


if __name__ == "__main__":
    main()

"""
Embed the Summa articles for semantic retrieval.

Semantic search is the precision upgrade over the keyword (BM25) floor: it matches on
meaning, so a question about the corpus's core themes finds the right article even when
they share no rare word (the "faith and reason" case the lexical demo cannot rank).

This builds the DOCUMENT side once - an embedding per Summa article - with OpenAI
`text-embedding-3-small` at 512 dimensions, L2-normalized so a query-time cosine is a
plain dot product. Vectors are written to data/embeddings/ (committed, ~3 MB) so that
with an OPENAI_API_KEY set the semantic demo works immediately, no re-embedding. The
query side is embedded at search time in demo/semantic.py.

Stdlib only (urllib); needs OPENAI_API_KEY. One-time cost is a few cents.

Usage:
  OPENAI_API_KEY=... python demo/embed.py
"""

from __future__ import annotations

import glob
import json
import math
import os
import struct
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMA = os.path.join(ROOT, "data", "summa")
OUT = os.path.join(ROOT, "data", "embeddings")

MODEL = "text-embedding-3-small"
DIMS = 512
BATCH = 96
MAX_CHARS = 28000     # ~8k tokens, the model's input ceiling; articles rarely hit this


def load_articles() -> list[dict]:
    docs = []
    for f in sorted(glob.glob(os.path.join(SUMMA, "*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    return docs


def embed_batch(texts: list[str], key: str) -> list[list[float]]:
    body = json.dumps({"model": MODEL, "input": texts, "dimensions": DIMS}).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings", data=body,
        headers={"authorization": f"Bearer {key}", "content-type": "application/json"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read())
            return [d["embedding"] for d in sorted(data["data"], key=lambda x: x["index"])]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 5:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"embedding failed: {e.code} {e.read().decode()[:200]}")
    raise SystemExit("embedding failed after retries")


def normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def main() -> None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY not set")
    docs = load_articles()
    print(f"embedding {len(docs)} Summa articles with {MODEL} ({DIMS}d)...")
    os.makedirs(OUT, exist_ok=True)

    ids: list[str] = []
    vec_path = os.path.join(OUT, "summa.f16.bin")
    total_tokens = 0
    with open(vec_path, "wb") as vf:
        for i in range(0, len(docs), BATCH):
            batch = docs[i:i + BATCH]
            texts = [((d.get("title", "") + "\n" + d["text"])[:MAX_CHARS]) for d in batch]
            vecs = embed_batch(texts, key)
            for d, v in zip(batch, vecs):
                nv = normalize(v)
                vf.write(struct.pack(f"<{DIMS}e", *nv))   # half-precision, compact
                ids.append(d["id"])
            print(f"  {min(i + BATCH, len(docs))}/{len(docs)}", end="\r")
    print()

    meta = {"model": MODEL, "dims": DIMS, "count": len(ids), "dtype": "float16",
            "normalized": True, "ids": ids}
    with open(os.path.join(OUT, "summa.meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    mb = os.path.getsize(vec_path) / 1e6
    print(f"wrote data/embeddings/summa.f16.bin ({mb:.2f} MB) + summa.meta.json "
          f"({len(ids)} vectors)")


if __name__ == "__main__":
    main()

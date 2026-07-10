"""
Semantic retrieval over the Summa - the precision upgrade over the BM25 floor.

Loads the document embeddings built by demo/embed.py, embeds the query at search time
with the same model, and ranks by cosine similarity (a dot product, since both sides
are L2-normalized). It refuses below a similarity floor, so an out-of-domain query
still gets an honest "not in the corpus" rather than the nearest unrelated article.

Same interface as retriever.Index: `.search(query, k) -> [(Doc, score)]`, so it is a
drop-in for the demo and the MCP server. Needs OPENAI_API_KEY (for the query) and the
committed vectors in data/embeddings/. Falls back to BM25 elsewhere; see demo/search.py.

Stdlib only (urllib).
"""

from __future__ import annotations

import glob
import json
import os
import struct

from retriever import Doc
from embed import embed_batch, normalize, MODEL, DIMS  # reuse the one embedder

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMA = os.path.join(ROOT, "data", "summa")
EMB = os.path.join(ROOT, "data", "embeddings")


class SemanticIndex:
    # Cosine floor below which we refuse. text-embedding-3-small puts an on-topic
    # question well above this and an out-of-domain one far below it; calibrated
    # against tests/test_retrieval_quality.py.
    SIM_FLOOR = 0.40

    def __init__(self, ids, vectors, docs):
        self.ids = ids              # list[str], row order of `vectors`
        self.vectors = vectors      # list[list[float]] normalized
        self.docs = [docs[i] for i in ids]

    def search(self, query, k=5):
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("semantic search needs OPENAI_API_KEY")
        q = normalize(embed_batch([query], key)[0])
        scored = []
        for i, v in enumerate(self.vectors):
            s = 0.0
            for a, b in zip(q, v):
                s += a * b
            scored.append((i, s))
        scored.sort(key=lambda t: t[1], reverse=True)
        if not scored or scored[0][1] < self.SIM_FLOOR:
            return []
        return [(self.docs[i], s) for i, s in scored[:k] if s >= self.SIM_FLOOR]


def _load_docs():
    docs = {}
    for f in sorted(glob.glob(os.path.join(SUMMA, "*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            docs[d["id"]] = Doc(d["id"], d["citation"], d.get("title", ""),
                                d["text"], d.get("source", {}))
    return docs


def available() -> bool:
    return (os.path.exists(os.path.join(EMB, "summa.meta.json"))
            and os.path.exists(os.path.join(EMB, "summa.f16.bin")))


def load_semantic() -> SemanticIndex:
    meta = json.load(open(os.path.join(EMB, "summa.meta.json"), encoding="utf-8"))
    dims = meta["dims"]
    ids = meta["ids"]
    raw = open(os.path.join(EMB, "summa.f16.bin"), "rb").read()
    row = dims * 2  # 2 bytes per float16
    vectors = [list(struct.unpack(f"<{dims}e", raw[i * row:(i + 1) * row]))
               for i in range(len(ids))]
    return SemanticIndex(ids, vectors, _load_docs())

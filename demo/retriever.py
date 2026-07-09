"""
Dependency-free retrieval over the Catena corpus.

A small BM25 index built in stdlib, so the demo runs with nothing installed. It is
deliberately lexical (keyword), not semantic. What that buys, precisely:

  * it NEVER fabricates - it only ever returns real, verbatim, cited source text;
  * it refuses when the query's terms are not in the corpus (out of domain);
  * it does NOT understand meaning, so it can surface a passage that merely shares
    a word with your query. That is a retrieval-quality limit, not a fidelity one -
    the passage shown is always real source, never invented.

Semantic (embedding) retrieval is the precision upgrade; see README. The point of
this floor is to prove the grounding discipline with zero setup.
"""

from __future__ import annotations

import glob
import json
import math
import os
import re
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "data")

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set(
    "the a an and or but of to in on for with as is are was were be been being "
    "that this these those it its he she they them his her their we you i not "
    "by from at into than then so if which who whom whose what when where how do "
    "does did done have has had may can could shall will would should must more "
    "most other any some such no nor thing things said unto thee thou thy hath "
    "doth also upon whether".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]


@dataclass
class Doc:
    id: str
    citation: str
    title: str
    text: str
    source: dict


class Index:
    # A query term anchors retrieval only if it is discriminative: present, and not
    # so common it carries no signal. This is what makes refusal work - a padded
    # query ("how do I ...") is not rescued by common words matching everything.
    DISCRIMINATIVE_MAX_DF = 0.12
    # Above this a term is too common to be what a query is "about".
    SALIENT_MAX_DF = 0.40
    # At least half of a query's salient terms must actually exist in the corpus,
    # or the query is about things we do not have -> refuse.
    MIN_COVERAGE = 0.5

    def __init__(self) -> None:
        self.docs: list[Doc] = []
        self.tf: list[dict] = []
        self.df: dict[str, int] = {}
        self.len: list[int] = []
        self.avgdl = 0.0

    def add(self, doc: Doc) -> None:
        toks = tokenize(doc.title + " " + doc.text)
        tf: dict[str, int] = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        for t in tf:
            self.df[t] = self.df.get(t, 0) + 1
        self.docs.append(doc)
        self.tf.append(tf)
        self.len.append(len(toks))

    def finalize(self) -> None:
        self.avgdl = (sum(self.len) / len(self.len)) if self.len else 0.0

    def _discriminative(self, query: str) -> list[str]:
        N = max(1, len(self.docs))
        return [t for t in dict.fromkeys(tokenize(query))
                if 0 < self.df.get(t, 0) <= self.DISCRIMINATIVE_MAX_DF * N]

    def _coverage(self, query: str) -> float:
        N = max(1, len(self.docs))
        salient = [t for t in dict.fromkeys(tokenize(query))
                   if self.df.get(t, 0) <= self.SALIENT_MAX_DF * N]
        if not salient:
            return 0.0
        return sum(1 for t in salient if self.df.get(t, 0) > 0) / len(salient)

    def search(self, query: str, k: int = 5, k1: float = 1.5, b: float = 0.75):
        terms = self._discriminative(query)
        # refuse: nothing to anchor on, or the query is mostly out-of-vocabulary
        if not terms or self._coverage(query) < self.MIN_COVERAGE:
            return []
        N = len(self.docs)
        scores = [0.0] * N
        for term in terms:
            df = self.df[term]
            idf = math.log(1 + (N - df + 0.5) / (df + 0.5))
            for i, tf in enumerate(self.tf):
                f = tf.get(term, 0)
                if not f:
                    continue
                denom = f + k1 * (1 - b + b * self.len[i] / self.avgdl)
                scores[i] += idf * (f * (k1 + 1)) / denom
        ranked = sorted(range(N), key=lambda i: scores[i], reverse=True)
        return [(self.docs[i], scores[i]) for i in ranked[:k] if scores[i] > 0]


def load_index() -> Index:
    """Build the lexical index over passage-level nodes (Summa articles now, patristic
    sections later). Individual Bible VERSES are deliberately excluded: they are far
    too short and numerous for this BM25 floor (they skew avgdl and the document-
    frequency thresholds the refusal logic depends on), and they are already reachable
    verbatim through verse resolution (lookup_verse / demo/refs) and, later, the
    semantic index. So the demo stays a grounded search over prose, and refusal stays
    calibrated."""
    idx = Index()
    files = sorted(glob.glob(os.path.join(CORPUS, "**", "*.jsonl"), recursive=True))
    if not files:
        raise SystemExit("no corpus found; run `python ingest/run.py --all` first")
    for path in files:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            n = json.loads(line)
            if n.get("type") == "verse":
                continue
            idx.add(Doc(n["id"], n["citation"], n.get("title", ""), n["text"], n.get("source", {})))
    idx.finalize()
    return idx

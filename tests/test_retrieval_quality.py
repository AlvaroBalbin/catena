"""
Retrieval quality gate for the keyless lexical demo.

The demo's search is the first thing a stranger runs, so it has to surface the right
passage for a plain question - AND still refuse when the query is out of domain. This
locks both with a fixed set of known-answer theology queries (ground truth pinned from
the corpus's own article titles) and a set of out-of-domain queries that must refuse.

Metric: hit@5 (an acceptable article in the top 5) for the answerable queries; every
out-of-domain query must return nothing. Run: python tests/test_retrieval_quality.py
"""

import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "demo"))
from retriever import load_index  # noqa: E402

# query -> the set of citations any of which counts as a correct top-5 hit. Where a
# question legitimately maps to a small cluster (God's existence, God's goodness), all
# members of the cluster are accepted. Ground truth verified against the corpus.
ANSWERABLE = {
    "is sacred doctrine a science": {"ST I, q.1, a.2"},
    "whether God exists": {"ST I, q.2, a.1", "ST I, q.2, a.2", "ST I, q.2, a.3"},
    "is God altogether simple": {"ST I, q.3, a.7"},
    "is God omnipotent": {"ST I, q.25, a.3"},
    "is God good": {"ST I, q.6, a.1", "ST I, q.6, a.2"},
    "does man have free will": {"ST I, q.83, a.1"},
    "does happiness consist in wealth": {"ST I-II, q.2, a.1"},
    "is it lawful to kill a man in self-defense": {"ST II-II, q.64, a.7"},
    "is charity a kind of friendship": {"ST II-II, q.23, a.1"},
    "is the human soul incorruptible": {"ST I, q.75, a.6"},
    "is faith a virtue": {"ST II-II, q.4, a.5"},
    "can the essence of God be seen with the bodily eye": {"ST I, q.12, a.3"},
    "do the angels have bodies": {"ST I, q.51, a.1"},
    "are there four cardinal virtues": {"ST I-II, q.61, a.2"},
    "will the body rise again in the resurrection": {"ST Suppl., q.75, a.1"},
    "does God love all things": {"ST I, q.20, a.1", "ST I, q.20, a.2"},
    "does God know things other than himself": {"ST I, q.14, a.5"},
    "the relationship between faith and reason": {
        # the harmony of faith and reason - accept the cluster that is squarely on it
        "ST I, q.1, a.1", "ST I, q.1, a.8", "ST II-II, q.2, a.4", "ST II-II, q.1, a.5"},
}

OUT_OF_DOMAIN = [
    "how do I configure a kubernetes ingress controller",
    "best recipe for chocolate chip cookies",
    "how to change a flat car tire",
    "what time does the pharmacy close",
]

# The queries the ranking fix specifically repairs: each is built entirely from the
# corpus's CENTRAL vocabulary, which the old rare-terms-only scoring filtered out and
# so wrongly refused. These must always hit - they are the regression this locks.
CORE_REGRESSION = {
    "is God good", "is faith a virtue", "does God love all things",
    "does God know things other than himself", "does man have free will",
    "whether God exists",
}

# Known lexical-ceiling misses: a plain BM25 keyword match cannot reliably rank these,
# because a rare incidental word ("relationship") outweighs the central ones. They are
# reported, not gated, and are exactly what semantic retrieval is meant to close.
KNOWN_LEXICAL_MISSES = {
    "the relationship between faith and reason",
    "will the body rise again in the resurrection",
}


def evaluate(idx, k=5, verbose=True):
    hits = 0
    misses = []
    core_misses = []
    for q, ok in ANSWERABLE.items():
        got = [d.citation for d, _ in idx.search(q, k=k)]
        if any(c in ok for c in got):
            hits += 1
        else:
            misses.append((q, got[:3]))
            if q in CORE_REGRESSION:
                core_misses.append(q)
    refused = 0
    leaked = []
    for q in OUT_OF_DOMAIN:
        got = idx.search(q, k=k)
        if not got:
            refused += 1
        else:
            leaked.append((q, got[0][0].citation))

    rate = hits / len(ANSWERABLE)
    if verbose:
        print(f"answerable hit@{k}: {hits}/{len(ANSWERABLE)} ({rate:.0%})")
        print(f"out-of-domain refused: {refused}/{len(OUT_OF_DOMAIN)}")
        for q, got in misses:
            tag = "known lexical ceiling" if q in KNOWN_LEXICAL_MISSES else "MISS"
            print(f"  [{tag}] '{q}' -> {got or 'REFUSED'}")
        for q, c in leaked:
            print(f"  [LEAK - should refuse] '{q}' -> {c}")
    return rate, refused, core_misses, leaked


def main():
    idx = load_index()
    rate, refused, core_misses, leaked = evaluate(idx)
    ok = rate >= 0.85 and not core_misses and not leaked
    if core_misses:
        print("FAIL: core-theme regression -", ", ".join(core_misses))
    print("OK: central-theme questions hit, nothing out-of-domain leaks"
          if ok else "FAIL: retrieval quality below bar")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

"""
Smoke test for the grounding discipline. Run: python tests/test_grounding.py

Locks the two behaviours the project promises: an in-corpus question retrieves a
real cited passage, and an out-of-domain question refuses. Loads the real corpus,
so run the ingest first.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "demo"))
from retriever import load_index  # noqa: E402


def main() -> None:
    idx = load_index()

    # in-corpus: must retrieve, and the top hit must be a real ST citation
    hits = idx.search("is sacred doctrine a science")
    assert hits, "expected a match for an in-corpus question"
    top, _ = hits[0]
    assert top.citation.startswith("ST "), top.citation
    assert top.text.strip(), "retrieved passage must have verbatim text"

    # a question built from the corpus's CENTRAL vocabulary must still ground: the
    # ranking must not filter out common-but-meaningful terms (the regression that
    # made "is God good" wrongly refuse). Full quality set: test_retrieval_quality.py.
    assert idx.search("is God good"), "expected a match for a central-theme question"

    # out of domain: must refuse (no hits) - the query's subject is not in the corpus
    assert not idx.search("how do I configure a kubernetes ingress controller"), \
        "expected refusal for an out-of-domain question"
    assert not idx.search("best recipe for chocolate chip cookies"), \
        "expected refusal for an out-of-domain question"

    print("OK: grounds in-corpus and central-theme questions, refuses out-of-domain")


if __name__ == "__main__":
    main()

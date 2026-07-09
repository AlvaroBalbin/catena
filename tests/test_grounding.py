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

    # out of domain: must refuse (no hits)
    assert not idx.search("how do I configure a kubernetes ingress controller"), \
        "expected refusal for an out-of-domain question"

    # vacuous (only common words): must refuse
    assert not idx.search("how do I do good things"), \
        "expected refusal for a vacuous query"

    print("OK: grounds in-corpus, refuses out-of-domain and vacuous queries")


if __name__ == "__main__":
    main()

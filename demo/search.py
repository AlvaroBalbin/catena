"""
One entry point that picks the best retrieval available.

Semantic (embedding) search is the precision upgrade, but it needs an OPENAI_API_KEY
(to embed the query) and the committed vectors in data/embeddings/. When both are
present we use it; otherwise we fall back to the zero-setup BM25 keyword index. Both
expose the same `.search(query, k) -> [(Doc, score)]`, so callers do not care which
they got - they just get the best one, and a refusal is still a refusal in either mode.
"""

from __future__ import annotations

import os

import retriever
import semantic


def load_search(prefer_semantic: bool = True):
    """Return (index, mode) where mode is 'semantic' or 'lexical'."""
    if (prefer_semantic and semantic.available()
            and os.environ.get("OPENAI_API_KEY")):
        try:
            return semantic.load_semantic(), "semantic"
        except Exception:
            pass  # any load/parse issue -> fall back rather than break the demo
    return retriever.load_index(), "lexical"

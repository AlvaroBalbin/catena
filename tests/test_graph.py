"""
Locks the citation graph. Run: python tests/test_graph.py
Build the graph first: python ingest/build_graph.py
"""

import json
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "ingest"))
from scripture import normalize_ref  # noqa: E402

GRAPH = os.path.join(ROOT, "data", "graph")


def test_normalizer():
    n = normalize_ref("2 Timothy 3:16")
    assert n["book"] == "2 Timothy" and n["chapter"] == 3 and n["verse_start"] == 16
    # Douay name maps to canonical
    assert normalize_ref("Ecclesiasticus 24:29")["book"] == "Sirach"
    # range expands
    assert normalize_ref("Psalm 90:15-16")["verse_keys"] == ["psalms/90/15", "psalms/90/16"]
    # non-references refuse
    assert normalize_ref("Holy Writ") is None


def test_graph():
    index = json.load(open(os.path.join(GRAPH, "scripture_index.json"), encoding="utf-8"))
    refs = json.load(open(os.path.join(GRAPH, "article_refs.json"), encoding="utf-8"))
    stats = json.load(open(os.path.join(GRAPH, "stats.json"), encoding="utf-8"))

    # the Word-made-flesh verse underpins the Incarnation questions
    j = index["john/1/14"]
    assert len(j) >= 15, len(j)
    assert any(h["id"].startswith("summa.st.iii.q1.") for h in j)

    # the existence-of-God proof rests on the divine name
    assert "Exodus 3:14" in refs["summa.st.i.q2.a3"]

    # coverage stays high (no silent regression)
    assert stats["parse_rate"] > 0.95, stats["parse_rate"]


if __name__ == "__main__":
    test_normalizer()
    test_graph()
    print("OK: normalizer canonicalizes and refuses; graph links verse<->article both ways")

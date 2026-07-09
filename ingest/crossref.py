"""
Internal cross-reference parsing.

The Summa constantly cites itself ("as stated above, I-II:1:8"). Those absolute
references use a rigid PART:QUESTION:ARTICLE form, which maps straight onto our node
ids. This turns article->article citations into graph edges.

We only resolve the unambiguous absolute form (PART:Q:A). Relative forms inside the
same question ("Article 1", "Reply to Objection 1") are intentionally left alone -
guessing their target would risk a wrong edge, and a wrong citation is worse than a
missing one for this project.
"""

from __future__ import annotations

import re

_PART_SLUG = {
    "I-II": "i-ii",
    "II-II": "ii-ii",
    "III": "iii",
    "SUPPLEMENT": "suppl",
    "SUPPL": "suppl",
    "I": "i",
}

# longer alternatives first so 'I-II'/'II-II' win over 'I'
_RX = re.compile(
    r"\b(I-II|II-II|III|Supplement|Suppl\.?|I)\s*:\s*(\d+)\s*:\s*(\d+)"
)


def parse_internal_refs(text: str) -> list[str]:
    """Return the node ids this text cites, in first-seen order, de-duplicated."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _RX.finditer(text):
        part = m.group(1).upper().rstrip(".")
        slug = _PART_SLUG.get(part)
        if not slug:
            continue
        nid = f"summa.st.{slug}.q{int(m.group(2))}.a{int(m.group(3))}"
        if nid not in seen:
            seen.add(nid)
            out.append(nid)
    return out

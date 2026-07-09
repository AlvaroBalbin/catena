"""
Summa Theologica ingest.

Parses New Advent question pages (public-domain Fathers of the English Dominican
Province translation, 1920-22) into Catena schema nodes, one node per article.

Design goals, in priority order:
  1. Lossless   - the article text is preserved verbatim; we only strip HTML
                  wrappers and resolve entities, never altering words.
  2. Addressable- every node gets a canonical citation and stable id.
  3. Verifiable - segments concatenate back to `text` exactly (asserted).

Stdlib only, so the repo installs with nothing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from html.parser import HTMLParser

# --- part model -----------------------------------------------------------

# New Advent numbers question pages <PART><QQQ>.htm where PART is:
#   1 -> Prima Pars (I), 2 -> Prima Secundae (I-II), 3 -> Secunda Secundae (II-II),
#   4 -> Tertia Pars (III), 5 -> Supplementum (Suppl.)
PARTS = {
    1: ("i", "I", "First Part"),
    2: ("i-ii", "I-II", "First Part of the Second Part"),
    3: ("ii-ii", "II-II", "Second Part of the Second Part"),
    4: ("iii", "III", "Third Part"),
    5: ("suppl", "Suppl.", "Supplement to the Third Part"),
}


# --- html -> verbatim text ------------------------------------------------

class _TextExtractor(HTMLParser):
    """Strips tags, keeps text verbatim. Entities are resolved by the parser
    (convert_charrefs defaults to True in py3), so 'Sirach&#160;3' -> 'Sirach 3'
    and em dashes etc. survive as their real characters."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def html_to_text(fragment: str) -> str:
    p = _TextExtractor()
    p.feed(fragment)
    # collapse internal whitespace runs to single spaces; trim ends. Words and
    # punctuation are untouched.
    return re.sub(r"\s+", " ", p.text()).strip()


# --- scripture references -------------------------------------------------

_BIBLE_LINK = re.compile(
    r'<a\s+href="[^"]*?/bible/[^"]*?"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL
)


def scripture_refs(fragment: str) -> list[dict]:
    """Every <a> pointing into New Advent's /bible/ tree is a Scripture citation;
    the anchor text is the human reference (e.g. 'Sirach 3:22')."""
    out: list[dict] = []
    seen: set[str] = set()
    for m in _BIBLE_LINK.finditer(fragment):
        ref = html_to_text(m.group(1))
        if ref and ref not in seen:
            seen.add(ref)
            out.append({"raw": ref, "kind": "scripture", "target_id": None})
    return out


# --- segment classification ----------------------------------------------

_SEG_RULES = [
    (re.compile(r"^Objection\s+(\d+)\.", re.I), "objection"),
    (re.compile(r"^On the contrary,", re.I), "sed-contra"),
    (re.compile(r"^I answer that,", re.I), "respondeo"),
    (re.compile(r"^Reply to Objection\s+(\d+)\.", re.I), "reply"),
]


def classify(seg_text: str) -> tuple[str, int | None]:
    for rx, role in _SEG_RULES:
        m = rx.match(seg_text)
        if m:
            n = int(m.group(1)) if m.groups() else None
            return role, n
    return "text", None


# --- page parsing ---------------------------------------------------------

_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_ARTICLE = re.compile(
    r'<h2\s+id="article(\d+)"[^>]*>(.*?)</h2>(.*?)(?=<h2\s+id="article|\Z)',
    re.I | re.S,
)
_PARA = re.compile(r"<p\b[^>]*>(.*?)</p>", re.I | re.S)
_QNO = re.compile(r"Question\s+(\d+)\.?\s*(.*)", re.I | re.S)
_ANO = re.compile(r"Article\s+(\d+)\.?\s*(.*)", re.I | re.S)


@dataclass
class Node:
    id: str
    work: str
    citation: str
    title: str
    path: list
    type: str
    text: str
    segments: list
    citations_out: list
    source: dict


def parse_question_page(html: str, part_num: int, source_url: str, retrieved: str) -> list[Node]:
    part_slug, part_disp, part_long = PARTS[part_num]

    h1 = _H1.search(html)
    q_raw = html_to_text(h1.group(1)) if h1 else ""
    qm = _QNO.match(q_raw)
    if not qm:
        raise ValueError(f"could not parse question heading: {q_raw!r}")
    q_no = int(qm.group(1))
    q_title = qm.group(2).strip()

    source = {
        "edition": "Fathers of the English Dominican Province, 2nd rev. ed. (1920-22)",
        "translator": "Fathers of the English Dominican Province",
        "license": "public-domain",
        "url": source_url,
        "retrieved": retrieved,
    }

    nodes: list[Node] = []
    for m in _ARTICLE.finditer(html):
        a_no = int(m.group(1))
        a_head = html_to_text(m.group(2))
        am = _ANO.match(a_head)
        a_title = am.group(2).strip() if am else a_head
        body_html = m.group(3)

        segments = []
        para_texts = []
        for pm in _PARA.finditer(body_html):
            frag = pm.group(1)
            txt = html_to_text(frag)
            if not txt:
                continue
            role, n = classify(txt)
            seg = {"role": role, "text": txt}
            if n is not None:
                seg["n"] = n
            segments.append(seg)
            para_texts.append(txt)

        text = "\n\n".join(para_texts)

        # collect scripture refs across the whole article body
        cites = scripture_refs(body_html)

        node = Node(
            id=f"summa.st.{part_slug}.q{q_no}.a{a_no}",
            work="summa-theologiae",
            citation=f"ST {part_disp}, q.{q_no}, a.{a_no}",
            title=a_title,
            path=[part_long, f"Question {q_no}: {q_title}", f"Article {a_no}"],
            type="article",
            text=text,
            segments=segments,
            citations_out=cites,
            source=source,
        )
        _assert_lossless(node)
        nodes.append(node)

    return nodes


def _assert_lossless(node: Node) -> None:
    """The core invariant: the segments must reproduce the text exactly."""
    rejoined = "\n\n".join(s["text"] for s in node.segments)
    if rejoined != node.text:
        raise AssertionError(
            f"lossless invariant broken for {node.id}: "
            f"segments do not rejoin to text"
        )
    if not node.text.strip():
        raise AssertionError(f"empty text for {node.id}")


def node_to_json(node: Node) -> str:
    return json.dumps(asdict(node), ensure_ascii=False)

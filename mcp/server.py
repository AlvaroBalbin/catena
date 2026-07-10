"""
Catena MCP server - a fact-checked Catholic backend for any AI.

Exposes the corpus and citation graph over the Model Context Protocol (stdio,
newline-delimited JSON-RPC 2.0) with no third-party dependencies, so any MCP client
(Claude, etc.) can ground a Catholic answer in real, cited source - or be told the
corpus does not contain it.

Tools:
  search(query, k)          grounded passages from the Summa + Roman Catechism, or a refusal
  get_article(citation)     the full verbatim article at an ST citation
  lookup_verse(reference)   verbatim verse text (Douay-Rheims + Vulgate Latin) + citers
  verse_fathers(reference)  the Church Fathers on a Gospel verse (Catena Aurea), verbatim
  article_scripture(citation)  the Scripture an article rests on

Run standalone:  python mcp/server.py   (then speak JSON-RPC on stdin)
Wire into a client: see mcp/README.md
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "demo"))
sys.path.insert(0, os.path.join(ROOT, "ingest"))
from search import load_search  # noqa: E402
from bible_text import verses_for, latin_for  # noqa: E402
from scripture import normalize_ref  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
GRAPH = os.path.join(ROOT, "data", "graph")

# --- corpus + graph loaded once ------------------------------------------

_IDX, _MODE = load_search()   # semantic if OPENAI_API_KEY + vectors present, else BM25
_BY_CITATION = {d.citation: d for d in _IDX.docs}
_BY_ID = {d.id: d for d in _IDX.docs}


def _load_graph(name: str):
    path = os.path.join(GRAPH, name)
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


_SCRIPTURE_INDEX = _load_graph("scripture_index.json")
_ARTICLE_REFS = _load_graph("article_refs.json")
_INTERNAL_REFS = _load_graph("internal_refs.json")
_INTERNAL_CITED_BY = _load_graph("internal_cited_by.json")
_FATHERS_INDEX = _load_graph("fathers_index.json")   # Gospel verse -> Catena Aurea pericopes


def _load_catena() -> dict:
    """The Catena Aurea pericopes by id, each carrying its ordered Father-attributed
    fragments - so the endpoint can return what the Fathers said on a verse, verbatim."""
    out = {}
    for f in glob.glob(os.path.join(ROOT, "data", "catena", "*.jsonl")):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if line:
                d = json.loads(line)
                out[d["id"]] = d
    return out


_CATENA_BY_ID = _load_catena()


def _citation_to_id(citation: str) -> str | None:
    if citation in _BY_CITATION:
        return _BY_CITATION[citation].id
    m = re.match(r"\s*ST\s+(I-II|II-II|III|Suppl\.|I)\s*,\s*q\.(\d+)\s*,\s*a\.(\d+)",
                 citation, re.I)
    if not m:
        return None
    part = m.group(1).lower().rstrip(".")
    return f"summa.st.{part}.q{m.group(2)}.a{m.group(3)}"


# --- tools ----------------------------------------------------------------

def tool_search(query: str, k: int = 3) -> str:
    hits = _IDX.search(query, k=k)
    if not hits:
        return (f'REFUSED: the corpus does not contain a clear answer to "{query}". '
                "Do not fabricate one; tell the user it is not in the source.")
    out = [f"{len(hits)} grounded passage(s). Cite the ST reference for any claim you use.\n"]
    for d, _ in hits:
        out.append(f"[{d.citation}] {d.title}\n{d.text}\n")
    return "\n".join(out)


def tool_get_article(citation: str) -> str:
    aid = _citation_to_id(citation)
    doc = _BY_ID.get(aid) if aid else None
    if not doc:
        return f'REFUSED: no article at "{citation}" in the corpus.'
    return f"[{doc.citation}] {doc.title}\n\n{doc.text}"


def tool_lookup_verse(reference: str) -> str:
    norm = normalize_ref(reference)
    if not norm:
        return f'Could not parse a Scripture reference from "{reference}".'
    key = norm["chapter_key"] if norm["verse_start"] is None else norm["verse_keys"][0]

    lines: list[str] = []
    verses = verses_for(norm)
    latin = latin_for(norm)
    if verses:
        label = "Douay-Rheims + Clementine Vulgate" if latin else "Douay-Rheims"
        lines.append(f'{norm["ref"]} ({label}, verbatim):')
        for d in verses:
            lines.append(f'  {d["citation"]} {d["text"]}')
            la = latin.get(f'{norm["slug"]}/{d["chapter"]}/{d["verse"]}')
            if la:
                lines.append(f'    (Vulgate: {la})')
        lines.append("")

    hits = _SCRIPTURE_INDEX.get(key, [])
    if hits:
        lines.append(f'{len(hits)} Summa article(s) lean on {norm["ref"]}:')
        for h in sorted(hits, key=lambda x: x["id"]):
            lines.append(f'  [{h["citation"]}] {h["title"]}')
    elif verses:
        lines.append(f'No Summa article cites {norm["ref"]}.')

    if _FATHERS_INDEX.get(key):
        lines.append(f'The Church Fathers comment on {norm["ref"]} in the Catena Aurea '
                     f'(call verse_fathers for the verbatim chain).')

    if not lines:
        return (f'The corpus contains no verse text and no article citing {norm["ref"]}.')
    return "\n".join(lines).strip()


def tool_verse_fathers(reference: str) -> str:
    """The patristic golden chain on a Gospel verse: what the Church Fathers said,
    verbatim, from Aquinas's Catena Aurea, each fragment attributed to its Father."""
    norm = normalize_ref(reference)
    if not norm:
        return f'Could not parse a Scripture reference from "{reference}".'
    if norm["verse_start"] is None:
        keys = sorted(k for k in _FATHERS_INDEX if k.startswith(norm["chapter_key"] + "/"))
    else:
        keys = norm["verse_keys"]
    seen, pericope_ids = set(), []
    for k in keys:
        for e in _FATHERS_INDEX.get(k, []):
            if e["id"] not in seen:
                seen.add(e["id"])
                pericope_ids.append(e["id"])
    if not pericope_ids:
        return (f'REFUSED: the Catena Aurea (Aquinas\'s patristic chain, the four Gospels '
                f'only) has no comment on {norm["ref"]}. Do not invent what the Fathers said.')
    out = [f'The Church Fathers on {norm["ref"]}, from Aquinas\'s Catena Aurea (verbatim - '
           f'attribute each quotation to the named Father):']
    for pid in pericope_ids:
        n = _CATENA_BY_ID.get(pid)
        if not n:
            continue
        out.append(f'\n{n["citation"]} - "{n["lemma"]}"')
        for s in n["segments"]:
            out.append(f'  [{s["father"]}] {s["text"]}')
    return "\n".join(out)


def tool_article_scripture(citation: str) -> str:
    aid = _citation_to_id(citation)
    if not aid:
        return f'Could not parse an ST citation from "{citation}".'
    refs = _ARTICLE_REFS.get(aid)
    if not refs:
        return f"{aid}: no Scripture citations recorded (or unknown article)."
    return f"{citation} rests on:\n" + "\n".join(f"  {r}" for r in refs)


def tool_cross_references(citation: str) -> str:
    aid = _citation_to_id(citation)
    if not aid:
        return f'Could not parse an ST citation from "{citation}".'
    cites = _INTERNAL_REFS.get(aid, [])
    citers = _INTERNAL_CITED_BY.get(aid, [])
    if not cites and not citers:
        return f"{citation}: no internal cross-references recorded (or unknown article)."
    lines = [f"{citation}:"]
    if cites:
        lines.append(f"  cites {len(cites)} article(s): " + ", ".join(c["citation"] for c in cites))
    if citers:
        lines.append(f"  is cited by {len(citers)} article(s): "
                     + ", ".join(sorted(c["citation"] for c in citers)))
    return "\n".join(lines)


TOOLS = [
    {
        "name": "search",
        "description": "Search the Summa Theologica and the Roman Catechism for grounded, "
                       "cited passages that answer a question. Returns verbatim source "
                       "with its citation (an ST reference or a Roman Catechism section), "
                       "or REFUSED if the corpus does not contain the answer. Cite the "
                       "reference for any claim you use; never fabricate beyond this.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "the question"},
                "k": {"type": "integer", "description": "how many passages (default 3)"},
            },
            "required": ["query"],
        },
        "handler": lambda a: tool_search(a["query"], int(a.get("k", 3))),
    },
    {
        "name": "get_article",
        "description": "Fetch the full verbatim article at a canonical citation, e.g. "
                       "'ST I, q.2, a.3'.",
        "inputSchema": {
            "type": "object",
            "properties": {"citation": {"type": "string"}},
            "required": ["citation"],
        },
        "handler": lambda a: tool_get_article(a["citation"]),
    },
    {
        "name": "lookup_verse",
        "description": "Return the verbatim text of a Scripture verse or chapter, e.g. "
                       "'John 1:14' or 'Romans 5' - the Douay-Rheims English and, in "
                       "parallel, the Clementine Vulgate Latin - together with every "
                       "Summa article that leans on it. Cite the reference for any "
                       "verse text you use; do not paraphrase it as your own.",
        "inputSchema": {
            "type": "object",
            "properties": {"reference": {"type": "string"}},
            "required": ["reference"],
        },
        "handler": lambda a: tool_lookup_verse(a["reference"]),
    },
    {
        "name": "verse_fathers",
        "description": "Return what the Church Fathers said on a Gospel verse, e.g. "
                       "'John 1:14' - the verbatim patristic chain from Aquinas's Catena "
                       "Aurea, each quotation attributed to its Father (Augustine, "
                       "Chrysostom, Bede, ...). Covers the four Gospels only; refuses "
                       "elsewhere. Attribute each quote to the named Father; never invent "
                       "a patristic source.",
        "inputSchema": {
            "type": "object",
            "properties": {"reference": {"type": "string"}},
            "required": ["reference"],
        },
        "handler": lambda a: tool_verse_fathers(a["reference"]),
    },
    {
        "name": "article_scripture",
        "description": "List the Scripture an article rests on, e.g. 'ST I, q.2, a.3'.",
        "inputSchema": {
            "type": "object",
            "properties": {"citation": {"type": "string"}},
            "required": ["citation"],
        },
        "handler": lambda a: tool_article_scripture(a["citation"]),
    },
    {
        "name": "cross_references",
        "description": "List the other Summa articles an article cites and is cited "
                       "by, e.g. 'ST I, q.2, a.3'. Walk the argument's structure.",
        "inputSchema": {
            "type": "object",
            "properties": {"citation": {"type": "string"}},
            "required": ["citation"],
        },
        "handler": lambda a: tool_cross_references(a["citation"]),
    },
]
_HANDLERS = {t["name"]: t["handler"] for t in TOOLS}


# --- JSON-RPC over stdio --------------------------------------------------

def _result(id_, result):
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_, code, message):
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def handle(msg: dict):
    """Return a response dict for a request, or None for a notification."""
    method = msg.get("method")
    id_ = msg.get("id")
    is_notification = "id" not in msg

    if method == "initialize":
        return _result(id_, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "catena", "version": "0.1.0"},
        })
    if method == "ping":
        return _result(id_, {})
    if method == "tools/list":
        listed = [{k: t[k] for k in ("name", "description", "inputSchema")} for t in TOOLS]
        return _result(id_, {"tools": listed})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        handler = _HANDLERS.get(name)
        if not handler:
            return _error(id_, -32602, f"unknown tool: {name}")
        try:
            text = handler(args)
        except Exception as e:
            return _result(id_, {"content": [{"type": "text", "text": f"ERROR: {e}"}],
                                 "isError": True})
        return _result(id_, {"content": [{"type": "text", "text": text}]})

    if is_notification:
        return None  # e.g. notifications/initialized
    return _error(id_, -32601, f"method not found: {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()

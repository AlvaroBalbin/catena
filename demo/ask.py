"""
Catena demo: ask a question, get a grounded, cited answer - or an honest refusal.

Two modes, chosen automatically:

  * retrieval-only (default, zero setup): returns the most relevant verbatim
    passages with their canonical citations. It literally cannot hallucinate,
    because it only ever shows you real source text. If nothing is relevant, it
    says so.

  * composed (optional): if ANTHROPIC_API_KEY or OPENAI_API_KEY is set, an LLM
    writes a short answer STRICTLY from the retrieved passages, cites the ST
    references inline, and is instructed to refuse if the passages do not contain
    the answer. The grounding is enforced by only ever giving the model the
    retrieved text - never its own memory.

Usage:
  python demo/ask.py "Is sacred doctrine a science?"
  python demo/ask.py --k 8 "Whether God exists?"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

from retriever import load_index, tokenize

# BM25 confidence floor below which we refuse rather than pretend.
FLOOR = 3.0


def refuse(query: str) -> None:
    print(f'\nThe corpus does not contain a clear answer to: "{query}"')
    print("(No passage scored above the relevance floor. Catena refuses rather "
          "than guess - that refusal is the point.)\n")


def show_passages(hits) -> None:
    print("\nPassages the corpus offers on your query (verbatim, cited, public "
          "domain - read them yourself; this is a lexical match, not a composed "
          "answer):\n")
    for doc, score in hits:
        print(f"  [{doc.citation}]  {doc.title}")
        snippet = " ".join(doc.text.split())
        if len(snippet) > 360:
            snippet = snippet[:360].rsplit(" ", 1)[0] + " ..."
        print(f"    {snippet}")
        print()


def compose_llm(query: str, hits) -> str | None:
    """Optional: compose a grounded answer if an API key is present. Returns None
    to fall back to retrieval-only."""
    anthropic = os.environ.get("ANTHROPIC_API_KEY")
    openai = os.environ.get("OPENAI_API_KEY")
    if not (anthropic or openai):
        return None

    context = "\n\n".join(
        f"[{d.citation}] {d.title}\n{d.text}" for d, _ in hits
    )
    system = (
        "You answer questions about the Summa Theologica of Thomas Aquinas. "
        "Answer ONLY from the passages provided below. Cite the ST reference in "
        "brackets (e.g. [ST I, q.2, a.3]) after each claim you draw from them. "
        "If the passages do not contain the answer, say plainly: 'The provided "
        "passages do not answer this.' Never use outside knowledge. Be concise."
    )
    user = f"Passages:\n\n{context}\n\nQuestion: {query}"

    try:
        if anthropic:
            return _anthropic(system, user, anthropic)
        return _openai(system, user, openai)
    except Exception as e:  # never let the optional layer break the demo
        print(f"(LLM layer unavailable: {e}; showing passages only)", file=sys.stderr)
        return None


def _anthropic(system: str, user: str, key: str) -> str:
    body = json.dumps({
        "model": "claude-sonnet-5",
        "max_tokens": 700,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return "".join(b.get("text", "") for b in data.get("content", []))


def _openai(system: str, user: str, key: str) -> str:
    body = json.dumps({
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions", data=body,
        headers={"authorization": f"Bearer {key}", "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="+")
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()
    query = " ".join(args.query)

    idx = load_index()
    hits = idx.search(query, k=args.k)

    # honest refusal: nothing relevant, or nothing above the floor
    if not hits or hits[0][1] < FLOOR:
        refuse(query)
        return

    answer = compose_llm(query, hits)
    if answer:
        print("\n" + answer.strip() + "\n")
        print("Sources:", ", ".join(f"[{d.citation}]" for d, _ in hits))
    else:
        show_passages(hits)


if __name__ == "__main__":
    main()

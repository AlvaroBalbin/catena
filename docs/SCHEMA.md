# Corpus schema

The unit of the corpus is a **node**: the smallest independently-citable piece of a text. For the Summa that is an *article*; for the Bible it will be a *verse*; for a patristic treatise a *section*. Every node is verbatim, addressable, and carries its provenance.

Nodes are stored as newline-delimited JSON (`.jsonl`), one node per line, plus a per-text `manifest.json`. Text is UTF-8, never lossy.

## Node

```jsonc
{
  "id": "summa.st.ii-ii.q1.a1",     // stable, globally unique, lowercase
  "work": "summa-theologiae",        // work slug (see manifest)
  "citation": "ST II-II, q.1, a.1",  // canonical human-readable citation
  "title": "Whether the object of faith is the First Truth?",
  "path": [                          // hierarchical location, human-readable
    "Second Part of the Second Part",
    "Question 1: Of Faith",
    "Article 1"
  ],
  "type": "article",                 // article | verse | section | chapter ...
  "text": "…full verbatim text of the whole article…",

  // For structured works (like the Summa), the internal parts are preserved
  // as ordered segments. Concatenating segment texts reproduces `text`.
  "segments": [
    { "role": "objection", "n": 1, "text": "…" },
    { "role": "objection", "n": 2, "text": "…" },
    { "role": "sed-contra", "text": "…" },
    { "role": "respondeo", "text": "…" },      // the corpus (body) of the article
    { "role": "reply", "n": 1, "text": "…" },
    { "role": "reply", "n": 2, "text": "…" }
  ],

  // Outbound references this node makes (Scripture, Fathers, other articles).
  // target_id is filled when the reference resolves to a node in the corpus.
  "citations_out": [
    { "raw": "John 14:6", "kind": "scripture", "target_id": null },
    { "raw": "ST I, q.16, a.5", "kind": "internal", "target_id": "summa.st.i.q16.a5" }
  ],

  "source": {
    "edition": "Fathers of the English Dominican Province, 2nd rev. ed. (1920-22)",
    "translator": "Fathers of the English Dominican Province",
    "license": "public-domain",
    "url": "…exact source URL…",
    "retrieved": "2026-07-09"
  }
}
```

### Verse node (Bible)

The Bible's citable unit is the verse. A verse node is the same shape with no
`segments` (a verse is atomic) and a few verse-specific fields:

```jsonc
{
  "id": "drb.john.1.14",             // drb.<slug>.<chapter>.<verse>
  "work": "douay-rheims",
  "citation": "John 1:14",           // canonical modern citation (the graph's form)
  "title": "",
  "path": ["New Testament", "John", "Chapter 1"],
  "type": "verse",
  "text": "And the Word was made flesh, and dwelt among us…",  // verbatim
  "book": "John",                    // canonical modern book name
  "douay_book": "John",              // book name as printed in this edition; differs
                                     //   for the historical books, e.g. "1 Kings" for
                                     //   what modern usage calls 1 Samuel
  "chapter": 1,
  "verse": 14,
  "verse_key": "john/1/14",          // the join key the citation graph uses
  "segments": [],
  "citations_out": [],
  "source": { "edition": "…Challoner…", "license": "public-domain", "via": "Project Gutenberg #1581", … }
}
```

The `verse_key` is what makes the Bible and the Summa's Scripture citations meet: a
citation "John 1:14" normalizes to `john/1/14` (see `ingest/scripture.py`) and the verse
node carries that exact key. Verse numbering follows the Vulgate/Douay convention the
Summa cites; the two documented normalizations (a Vulgate psalm split and one duplicate
label) are recorded in `data/bible/manifest.json`.

### Field rules

- **`id`** - deterministic from the citation, never reused, never renumbered. This is the join key for cross-references and embeddings.
- **`text`** - verbatim. If the source has it, we keep it exactly, including archaic spelling. No normalization that changes words. Whitespace may be normalized (collapse runs, trim) but nothing else.
- **`segments`** - present for works with regular internal structure (the Summa). `text` MUST equal the segments concatenated in order (with single blank-line joins), so nothing is lost and the split is verifiable. A validator enforces this.
- **`citations_out`** - captured as raw strings at ingest; resolved to `target_id`s in a second pass once all nodes exist. Unresolved refs (e.g. to a Father not yet in the corpus) keep `target_id: null` - honest about what we can and cannot link.
- **`source`** - mandatory. A node with no verified source does not ship.

## Manifest (`manifest.json`, per work)

```jsonc
{
  "work": "summa-theologiae",
  "title": "Summa Theologica",
  "author": "Thomas Aquinas",
  "edition": "Fathers of the English Dominican Province, 2nd rev. ed. (1920-22)",
  "license": "public-domain",
  "source": "…",
  "retrieved": "2026-07-09",
  "structure": ["part", "question", "article"],
  "counts": { "parts": 0, "questions": 0, "articles": 0 },   // filled by validator
  "expected_counts": { "articles": 2669 },                   // known from the edition, to catch gaps
  "node_count": 0
}
```

`expected_counts` is how we prove the corpus is *complete*, not just non-empty: the validator compares ingested counts against the known structure of the edition and fails loudly on any gap. A partial corpus is never presented as whole.

## Validation invariants (enforced by `ingest/validate`)

1. Every node has a unique `id` and a non-empty `text` and a `source`.
2. For segmented nodes, `join(segments) == text`.
3. `counts` match `expected_counts` for the work (no missing questions/articles).
4. Every `citation` parses back to the node's structural position.
5. No node's `text` is a truncation (no trailing "…" injected by a scraper; length sanity vs. source).

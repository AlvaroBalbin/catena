# Catena

**An open, structured, verbatim, and fully-cited corpus of the Catholic tradition, built for grounded retrieval.**

Most "Catholic AI" fails at one thing: it invents. It answers with confidence and no source, or misattributes a teaching, or paraphrases the Magisterium into something it never said. Catena exists to make the opposite easy.

Catena is a clean, machine-readable corpus of public-domain Catholic texts where **every unit of text carries a canonical citation** (e.g. `ST II-II, q.1, a.1`), the text is stored **verbatim** (never paraphrased or truncated), and the retrieval demo is built to **cite or refuse** - it answers only from what it actually retrieved, quotes the source, and says "I don't have that in the corpus" rather than guessing.

The name is from the *Catena Aurea*, Aquinas's "golden chain" of sourced quotations from the Church Fathers. The point then was the same as now: never assert without a source in the chain.

## What this is (and is not)

- **It is a dataset + a reference retrieval demo.** The dataset is the deliverable. The demo exists to prove the discipline (grounded, cited, refuses to hallucinate), not to be a product.
- **It is only public-domain and freely-licensed texts.** We do not, and will not, redistribute copyrighted texts (the modern Catechism, modern encyclical translations, modern Bible translations) without written permission from the rights holder. See [`data/SOURCES.md`](data/SOURCES.md) for the per-text rights map. Doing this wrong - pirating the Church's own texts under an "open" banner - would betray the whole point.

## The three disciplines

1. **Lossless.** Text is captured verbatim from the source edition. No summarization, no silent truncation, no cleanup that changes words.
2. **Addressable.** Every unit has a stable, canonical citation so any answer can quote it exactly and a reader can verify it in a print edition.
3. **Grounded.** The demo answers strictly from retrieved units, always shows its citations, and refuses when the corpus does not contain the answer. The refusal is a feature.

## Corpus (v1 and roadmap)

| Text | Edition / translation | Rights | Status |
|------|----------------------|--------|--------|
| Summa Theologica | Fathers of the English Dominican Province, 2nd ed. 1920-22 | Public domain | in corpus (3,115 articles) |
| Douay-Rheims Bible | Challoner revision (Project Gutenberg #1581) | Public domain | in corpus (35,786 verses, 73 books) |
| Church Fathers | Schaff, Ante/Nicene/Post-Nicene Fathers, 1885-1900 | Public domain | roadmap |
| Clementine Vulgate | 1592 | Public domain | roadmap |
| Older encyclicals / councils | pre-1930 English translations | Public domain (verify per-doc) | roadmap |
| Catechism of the Catholic Church | USCCB/LEV | **Copyright - permission track** | not redistributed; see SOURCES.md |

## Layout

```
catena/
  data/
    SOURCES.md        # per-text rights map and provenance (READ THIS FIRST)
    summa/            # ingested corpus, one file per unit + a manifest
  docs/
    SCHEMA.md         # the corpus data model
    graph/            # the citation graph (verse -> articles, article -> refs, stats)
  ingest/             # ingest scripts, reference normalizer, graph builder, validator
  demo/               # grounded cite-or-refuse retrieval + graph-walking tools
  mcp/                # MCP server: ground any AI in the corpus
  tests/              # grounding, graph, and MCP smoke tests
  LICENSE             # MIT (covers the CODE only; text licenses are per-source)
```

## Try it

No install, no keys:

```bash
python ingest/run.py --all      # build the Summa from source (one-time, ~10 min, polite)
python ingest/bible.py          # add the Douay-Rheims Bible (35,786 verses, one fetch)
python ingest/validate.py       # prove it: lossless, addressable, complete
python demo/ask.py "is sacred doctrine a science"
```

```
Passages the corpus offers on your query (verbatim, cited, public domain - read
them yourself; this is a lexical match, not a composed answer):

  [ST I, q.1, a.2]  Whether sacred doctrine is a science?
    Objection 1. It seems that sacred doctrine is not a science. For every science
    proceeds from self-evident principles. But sacred doctrine proceeds from
    articles of faith which are not self-evident ... "For all men have not faith"
    (2 Thessalonians 3:2). ...
```

Ask it something the corpus does not contain and it refuses instead of guessing:

```
$ python demo/ask.py "how do I configure a kubernetes ingress controller"
The corpus does not contain a clear answer to: "how do I configure a kubernetes
ingress controller"
(No passage scored above the relevance floor. Catena refuses rather than guess -
that refusal is the point.)
```

If `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is set, the demo will additionally
compose a short answer **strictly from the retrieved passages**, citing the ST
references inline, and refuse if those passages do not contain the answer.

## What the demo guarantees (and what it does not)

Precisely, so the claim is honest:

- **It never fabricates.** It only ever returns real, verbatim source text with a
  citation. There is no path by which it can invent a teaching.
- **It refuses out of domain.** If your question's terms are not in the corpus, it
  says so rather than reaching.
- **It is lexical, not semantic (default).** Zero-setup retrieval matches keywords,
  so it can surface a passage that merely shares a word with your query. That is a
  retrieval-*quality* limit, not a fidelity one - the passage shown is still real,
  cited source, never invented. Semantic retrieval (below) is the fix.

## Walk the golden chain (citation graph)

Catena is not a flat pile of text. Every Scripture reference an article makes is an
*edge*, so you can walk the tradition. Build the graph once
(`python ingest/build_graph.py`), then:

```bash
python demo/refs.py "John 1:14"          # every article that leans on a verse
python demo/refs.py "Romans 5"           # every article citing a whole chapter
python demo/refs.py --article "ST I, q.2, a.3"   # what an article rests on AND what cites it
python demo/refs.py --top                # what the Summa leans on most
```

```
$ python demo/refs.py --article "ST I, q.2, a.3"
summa.st.i.q2.a3
  rests on 1 Scripture reference(s):
    Exodus 3:14
  is cited by 13 other article(s):
    [ST I, q.3, a.7]  Whether God is altogether simple?
    [ST I, q.25, a.3] Whether God is omnipotent?
    ...
```

The existence-of-God proof rests on the divine name ("I AM WHO I AM", Exodus 3:14)
and is the foundation the entire treatise on the divine nature builds on - now
queryable edges. Across the corpus:

- **8,491 Scripture citations** resolved (96.8%) into **4,924 verse nodes**;
  most-cited verse John 1:14, most-cited books Matthew, Romans, 1 Corinthians.
- **3,775 internal article-to-article edges** (99% resolved). By inbound citations
  the load-bearing article of the whole Summa is **ST I, q.84, a.7** (the intellect
  "turning to phantasms") - its structural backbone, made visible.

The `data/graph/` artifacts are open data in their own right.

## The verse behind the citation

The Scripture graph told you *which* articles lean on a verse. With the Douay-Rheims
Bible in the corpus (the Challoner revision, the Bible whose Vulgate numbering the
Summa's own citations use), those citations now resolve to the **actual verse text**,
verbatim and cited:

```bash
python demo/refs.py "John 1:14"
```

```
John 1:14 (Douay-Rheims, verbatim, public domain):

  John 1:14  And the Word was made flesh and dwelt among us (and we saw his glory,
             the glory as it were of the only begotten of the Father), full of grace
             and truth.

23 article(s) lean on John 1:14 (verse):
  [ST I-II, q.108, a.1]  Whether the New Law ought to prescribe or prohibit any external acts?
  [ST III, q.1, a.3]     Whether, if man had not sinned, God would have become incarnate?
  ...
```

The Bible was ingested to the same three disciplines as the Summa: each of the 35,786
verses is verbatim (lossless-verified against the source), addressable
(`john/1/14`, the exact key the citation graph uses), and complete (all 73 books of the
Catholic canon, every chapter, contiguous verse numbering, proven by the validator).
Because it is the Douay-Rheims, its Vulgate psalm numbering lines up with the Summa's
citations where a modern Bible would not - so **99.4%** of the Summa's Scripture
citations resolve to real verse text (the small remainder are citations that reference a
verse number the chapter does not have - garbled source citations, honestly left
unresolved rather than forced). Provenance and the one naming seam (the Douay
"1 Kings" = 1 Samuel convention) are documented in [`data/SOURCES.md`](data/SOURCES.md).

## Roadmap

- **Semantic retrieval** - embed the corpus so retrieval is by meaning, not
  keywords, with an honest similarity floor for refusal. Precision upgrade over the
  lexical default.
- **Resolve the rest of the graph** - Scripture edges are built; internal `ST`
  cross-references and citations of the Fathers/Aristotle are next, to complete the
  navigable web.
- **A fidelity benchmark** - grounded-Catholic-QA where every answer must be
  entailed by its cited passages, scored on citation accuracy and refusal calibration.

## Ground any AI in it (MCP)

Catena ships an MCP server so any assistant (Claude, etc.) can ground a Catholic
answer in real, cited source - or be told the corpus does not contain it. Stdlib
only, standard stdio JSON-RPC.

```bash
claude mcp add catena -- python /absolute/path/to/catena/mcp/server.py
```

Tools: `search` (grounded passages or a refusal), `get_article`, `lookup_verse`
(now returns the verbatim Douay-Rheims verse text plus the articles that lean on it),
`article_scripture`, `cross_references`. See [`mcp/README.md`](mcp/README.md).
- **More public-domain texts** - Church Fathers (Schaff), the Clementine Vulgate
  (parallel Latin), pre-1930 encyclicals and councils, each with a verified
  `SOURCES.md` entry.
- **Catechism** - only if/when USCCB grants written permission (see
  [`docs/catechism-permission-request.md`](docs/catechism-permission-request.md)).

## Licensing

The **code** in this repository is MIT (see [`LICENSE`](LICENSE)). The **texts** carry their own licenses, documented per-source in [`data/SOURCES.md`](data/SOURCES.md); public-domain texts are redistributed with their edition and translator attributed.

## Status

Early. v1 is the Summa. Foundations first, then scale one text at a time with structural validation - never a partial or unverified corpus passed off as complete.

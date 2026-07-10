# Catena

**The grounding layer for Catholic AI: an open, verbatim, fully-cited corpus of the tradition, with a citation graph and a cite-or-refuse endpoint any assistant can build on.**

Most "Catholic AI" fails at one thing: it invents. It answers with confidence and no source, misattributes a teaching, or paraphrases the Magisterium into something it never said. For a parish, a publisher, or a diocese that is not a rough edge - it is a machine that misquotes the Church, a liability no institution can put its name on. Catena exists to make the opposite the easy path.

Catena is a clean, machine-readable corpus of public-domain Catholic texts where **every unit of text carries a canonical citation** (e.g. `ST II-II, q.1, a.1`), the text is stored **verbatim** (never paraphrased or truncated), and retrieval is built to **cite or refuse** - it answers only from what it actually retrieved, quotes the source, and says "I don't have that in the corpus" rather than guessing. Point an assistant at it, over the MCP endpoint or the dataset, and its Catholic answers come back as real cited source or an honest refusal.

The name is from the *Catena Aurea*, Aquinas's "golden chain" of sourced quotations from the Church Fathers, now itself in the corpus. The point then was the same as now: never assert without a source in the chain.

## For builders and institutions

If you are building anything that answers questions about the Catholic faith - an app, a study tool, a parish or diocesan assistant, a publisher's back catalogue - you have one hard problem: it must not invent doctrine. Catena is the layer that solves it, and it is free and open to adopt:

- **Ground your assistant in it over MCP.** One line wires the endpoint into an MCP client ([below](#ground-any-ai-in-it-mcp)); every answer is verbatim cited source or an explicit refusal. No fine-tune, no prompt-craft, no hallucinated Councils.
- **Or load the dataset.** The whole corpus and citation graph are on the Hugging Face Hub, one `load_dataset` call ([below](#load-the-dataset-hugging-face)).
- **Verifiable by design.** Every unit traces to a named print edition, so any claim can be checked against the book on a shelf. That is the property an institution actually needs before it trusts a machine with its teaching.
- **Your own texts, grounded the same way.** The open corpus is public-domain text. The same discipline extends to an organisation's own material (catechetical resources, an order's archive, a bishop's writings), grounded and cited under permission rather than scraped. If that is you, open an issue or reach out.

Nothing is charged to use the open corpus. The aim is to make grounded, honest Catholic AI the default, and to be the reference layer it stands on.

## Try it live (no install)

**[Open the explorer &#8594;](https://alvarobalbin.github.io/catena/explorer/)** - ask a question and read the actual passages Aquinas wrote and the Church Fathers he chained together, verbatim and cited; on any Gospel verse, read what the Fathers said, in their own words; walk the Scripture behind it in English and the Latin Vulgate; watch it refuse when the corpus does not contain the answer. It runs entirely in your browser over the open data in this repo - no server, no key, nothing you type leaves the page.

## Load the dataset (Hugging Face)

The corpus is published as a dataset on the Hugging Face Hub, loadable in one line - the Summa, both Bibles, and the citation graph as tabular edges:

```python
from datasets import load_dataset

summa  = load_dataset("TheAlvaroBalbin/catena", "summa")               # 3,115 articles
verses = load_dataset("TheAlvaroBalbin/catena", "douay_rheims")        # 35,786 verses (English)
latin  = load_dataset("TheAlvaroBalbin/catena", "clementine_vulgate")  # 35,809 verses (Latin)
edges  = load_dataset("TheAlvaroBalbin/catena", "scripture_edges")     # article -> verse citation graph
```

Dataset: **https://huggingface.co/datasets/TheAlvaroBalbin/catena**

## What this is (and is not)

- **It is infrastructure, not a chatbot.** The deliverable is the corpus, the citation graph, and the grounding endpoint - the layer other things build on. The explorer and the CLI demo exist to *prove* the discipline (grounded, cited, refuses to hallucinate) on a page you can check for yourself, not to be the product themselves.
- **It is only public-domain and freely-licensed texts.** We do not, and will not, redistribute copyrighted texts (the modern Catechism, modern encyclical translations, modern Bible translations) without written permission from the rights holder. See [`data/SOURCES.md`](data/SOURCES.md) for the per-text rights map. Doing this wrong - pirating the Church's own texts under an "open" banner - would betray the whole point.

## The three disciplines

1. **Lossless.** Text is captured verbatim from the source edition. No summarization, no silent truncation, no cleanup that changes words.
2. **Addressable.** Every unit has a stable, canonical citation so any answer can quote it exactly and a reader can verify it in a print edition.
3. **Grounded.** The demo answers strictly from retrieved units, always shows its citations, and refuses when the corpus does not contain the answer. The refusal is a feature.

## Corpus (v1 and roadmap)

| Text | Edition / translation | Rights | Status |
|------|----------------------|--------|--------|
| Summa Theologica | Fathers of the English Dominican Province, 2nd ed. 1920-22 | Public domain | in corpus (3,115 articles) |
| Catena Aurea (Church Fathers on the Gospels) | Newman / Oxford translation, 1841-45 | Public domain | in corpus (814 pericopes, 12,692 fragments, 51 Fathers, verse-keyed) |
| Douay-Rheims Bible | Challoner revision (Project Gutenberg #1581) | Public domain | in corpus (35,786 verses, 73 books) |
| Clementine Vulgate | Sixto-Clementine 1592 (Clementine Vulgate Project e-text) | Public domain | in corpus (35,809 verses, parallel Latin) |
| Church Fathers (full works) | Schaff, Ante/Nicene/Post-Nicene Fathers, 1885-1900 | Public domain | roadmap |
| Older encyclicals / councils | pre-1930 English translations | Public domain (verify per-doc) | roadmap |
| Catechism of the Catholic Church | USCCB/LEV | **Copyright - permission track** | not redistributed; see SOURCES.md |

## Layout

```
catena/
  data/
    SOURCES.md        # per-text rights map and provenance (READ THIS FIRST)
    summa/            # ingested corpus, one file per unit + a manifest
    bible/            # drb/ (Douay-Rheims English) + vg/ (Clementine Vulgate Latin)
  docs/
    SCHEMA.md         # the corpus data model
    graph/            # the citation graph (verse -> articles, article -> refs, stats)
  ingest/             # ingest scripts, reference normalizer, graph builder, validator
  demo/               # grounded cite-or-refuse retrieval + graph-walking tools
  explorer/           # the zero-install web explorer (one static page over the data)
  mcp/                # MCP server: ground any AI in the corpus
  tests/              # grounding, graph, retrieval-quality, and MCP smoke tests
  LICENSE             # MIT (covers the CODE only; text licenses are per-source)
```

## Run it locally

The built corpus is committed, so the demos work straight from a clone - no keys, no
ingest step:

```bash
python demo/ask.py "is sacred doctrine a science"   # grounded, cited answer or a refusal
python demo/refs.py "John 1:14"                      # walk the golden chain from a verse
python -m http.server -d explorer 8000              # then open localhost:8000 for the explorer
```

To rebuild the corpus from source instead of using the committed data:

```bash
python ingest/run.py --all      # build the Summa from source (one-time, ~10 min, polite)
python ingest/bible.py          # add the Douay-Rheims Bible (35,786 verses, one fetch)
python ingest/vulgate.py        # add the Clementine Vulgate Latin, in parallel (35,809 verses)
python ingest/validate.py       # prove it: lossless, addressable, complete
python explorer/build.py        # rebuild the explorer's data bundle
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

### Semantic search (optional, higher precision)

Keyword search matches words; **semantic search matches meaning**, so a question about
the corpus's core themes finds the right article even when they share no rare word. It
is built in and switches on automatically when an `OPENAI_API_KEY` is set:

```bash
python demo/embed.py                      # one-time: embed the corpus (~$0.05, committed)
python demo/ask.py "the relationship between faith and reason"
```

With keyword search that query returns articles on *marriage impediments* (they share
the incidental word "relationship"); with semantic search it returns
`ST II-II, q.2, a.4` - *"Whether it is necessary to believe those things which can be
proved by natural reason?"* - the article actually about faith and reason. On a fixed
18-question eval, hit@5 goes from 89% (keyword) to **100%** (semantic), and every
out-of-domain query still refuses. The document vectors are committed
(`data/embeddings/`), so only the query is embedded at search time; with no key it
falls back to the keyword index. The MCP server uses whichever is available.

## What the demo guarantees (and what it does not)

Precisely, so the claim is honest:

- **It never fabricates.** It only ever returns real, verbatim source text with a
  citation. There is no path by which it can invent a teaching.
- **It refuses out of domain.** If your question is not about something in the corpus,
  it says so rather than reaching - in both keyword and semantic mode.
- **Keyword by default, semantic with a key.** Zero-setup retrieval matches keywords,
  so it can surface a passage that merely shares a word with your query - a
  retrieval-*quality* limit, not a fidelity one (the passage is still real, cited
  source, never invented). Semantic search (above) closes that gap.

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

## The verse behind the citation - in two languages

The Scripture graph told you *which* articles lean on a verse. With the Douay-Rheims
Bible in the corpus (the Challoner revision, whose Vulgate numbering the Summa's own
citations use) **and the Clementine Vulgate** beside it, a citation now resolves to the
**actual verse text** - the English *and* the Latin Aquinas actually quoted - verbatim
and cited:

```bash
python demo/refs.py "John 1:14"
```

```
John 1:14 (Douay-Rheims + Clementine Vulgate, verbatim, public domain):

  John 1:14  And the Word was made flesh and dwelt among us (and we saw his glory,
             the glory as it were of the only begotten of the Father), full of grace
             and truth.
             (Et Verbum caro factum est, et habitavit in nobis : et vidimus gloriam
              ejus, gloriam quasi unigeniti a Patre plenum gratiæ et veritatis.)

23 article(s) lean on John 1:14 (verse):
  [ST I-II, q.108, a.1]  Whether the New Law ought to prescribe or prohibit any external acts?
  [ST III, q.1, a.3]     Whether, if man had not sinned, God would have become incarnate?
  ...
```

Both Bibles were ingested to the same three disciplines as the Summa. Each of the
35,786 Douay verses and 35,809 Clementine Vulgate verses is verbatim (lossless-verified
against the source - the Latin is re-derived from the raw edition under one documented
markup rule and must match exactly), addressable (`john/1/14`, the exact key the
citation graph uses), and complete (all 73 books of the Catholic canon, every chapter,
contiguous verse numbering, proven by the validator). Because both follow Vulgate
numbering, they line up with the Summa's citations where a modern Bible would not - so
**99.4%** of the Summa's Scripture citations resolve to English verse text and **99.5%**
to Latin. The two Bibles parallel each other verse-for-verse across **99.9%** of
addresses; the handful that do not meet are concentrated in the Psalms, where the two
editions split a few verses differently - measured and recorded, never forced.
Provenance, the markup rule, and the naming seams are documented in
[`data/SOURCES.md`](data/SOURCES.md).

## Roadmap

- **Resolve the rest of the graph** - Scripture edges are built; internal `ST`
  cross-references and citations of the Fathers/Aristotle are next, to complete the
  navigable web.
- **A fidelity benchmark** - grounded-Catholic-QA where every answer must be
  entailed by its cited passages, scored on citation accuracy and refusal calibration.

## Ground any AI in it (MCP)

This is the grounding endpoint builders integrate. Catena ships an MCP server so any
assistant (Claude, etc.) can ground a Catholic answer in real, cited source - or be told
the corpus does not contain it. Stdlib only, standard stdio JSON-RPC.

```bash
claude mcp add catena -- python /absolute/path/to/catena/mcp/server.py
```

Tools: `search` (grounded passages or a refusal), `get_article`, `lookup_verse`
(returns the verbatim Douay-Rheims English and the parallel Clementine Vulgate Latin,
plus the articles that lean on the verse), `verse_fathers` (the Church Fathers on a
Gospel verse, verbatim, from the Catena Aurea, each quotation attributed to its Father),
`article_scripture`, `cross_references`. See [`mcp/README.md`](mcp/README.md).
- **More public-domain texts** - Church Fathers (Schaff), pre-1930 encyclicals and
  councils, each with a verified `SOURCES.md` entry.
- **Catechism** - only if/when USCCB grants written permission (see
  [`docs/catechism-permission-request.md`](docs/catechism-permission-request.md)).

## Licensing

The **code** in this repository is MIT (see [`LICENSE`](LICENSE)). The **texts** carry their own licenses, documented per-source in [`data/SOURCES.md`](data/SOURCES.md); public-domain texts are redistributed with their edition and translator attributed.

## Status

Early but real. The Summa, the Catena Aurea (the Fathers on the four Gospels), and both Bibles are in the corpus, each structurally validated. Foundations first, then scale one text at a time - never a partial or unverified corpus passed off as complete.

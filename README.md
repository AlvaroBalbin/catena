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
| Summa Theologica | Fathers of the English Dominican Province, 2nd ed. 1920-22 | Public domain | v1 (in progress) |
| Church Fathers | Schaff, Ante/Nicene/Post-Nicene Fathers, 1885-1900 | Public domain | roadmap |
| Douay-Rheims Bible | Challoner revision | Public domain | roadmap |
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
  ingest/             # source-specific ingest scripts (source -> schema)
  demo/               # grounded cite-or-refuse retrieval demo
  LICENSE             # MIT (covers the CODE only; text licenses are per-source)
```

## Try it

No install, no keys:

```bash
python ingest/run.py --all      # build the corpus from source (one-time, ~10 min, polite)
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
python demo/refs.py --article "ST I, q.2, a.3"   # the verses an article rests on
python demo/refs.py --top                # the Scripture the Summa leans on most
```

```
$ python demo/refs.py --article "ST I, q.2, a.3"
summa.st.i.q2.a3 rests on 1 Scripture reference(s):
  Exodus 3:14
```

That is the existence-of-God proof resting on the divine name, "I AM WHO I AM" -
now a queryable edge. Across the corpus: **8,491 Scripture citations resolved
(96.8%)** into **4,924 verse nodes**. The most-cited verse is John 1:14, "the Word
was made flesh"; the most-cited books are Matthew, Romans, and 1 Corinthians. The
`data/graph/` artifacts are open data in their own right.

## Roadmap

- **Semantic retrieval** - embed the corpus so retrieval is by meaning, not
  keywords, with an honest similarity floor for refusal. Precision upgrade over the
  lexical default.
- **Resolve the rest of the graph** - Scripture edges are built; internal `ST`
  cross-references and citations of the Fathers/Aristotle are next, to complete the
  navigable web.
- **A fidelity benchmark** - grounded-Catholic-QA where every answer must be
  entailed by its cited passages, scored on citation accuracy and refusal calibration.
- **MCP grounding layer** - expose the corpus and graph as tools so any AI can
  ground a Catholic answer in real citations, or refuse.
- **More public-domain texts** - Church Fathers (Schaff), Douay-Rheims + Vulgate,
  pre-1930 encyclicals and councils, each with a verified `SOURCES.md` entry.
- **Catechism** - only if/when USCCB grants written permission (see
  [`docs/catechism-permission-request.md`](docs/catechism-permission-request.md)).

## Licensing

The **code** in this repository is MIT (see [`LICENSE`](LICENSE)). The **texts** carry their own licenses, documented per-source in [`data/SOURCES.md`](data/SOURCES.md); public-domain texts are redistributed with their edition and translator attributed.

## Status

Early. v1 is the Summa. Foundations first, then scale one text at a time with structural validation - never a partial or unverified corpus passed off as complete.

# The Catena explorer

A single, self-contained web page that lets anyone use the corpus with no install and
no key: ask a question and read the actual passages Aquinas wrote (verbatim, cited),
walk the citation graph from a verse to every article that leans on it, read the
parallel Latin of the Vulgate, and watch it refuse when the corpus does not contain the
answer.

**Live:** https://alvarobalbin.github.io/catena/explorer/

## How it works

- `index.html` is the whole app: vanilla JavaScript, no framework, no build step, no
  server. It runs entirely in the browser and nothing you type leaves the page.
- It loads two precomputed JSON files from `data/`:
  - `core.json` (loads first): article titles, the whole citation graph, and the
    verbatim text (English + Latin) of every verse the Summa cites. Enough to browse
    the golden chain, look up a verse in both languages, and search by title - instantly.
  - `bodies.json` (loads next): the full verbatim text of every article, which upgrades
    search to full text and lets you read an article in full.
- The in-browser search is a faithful port of `demo/retriever.py` - the same BM25, the
  same stopwords, the same cite-or-refuse thresholds - so the live search behaves
  exactly like the tested Python demo.

## Rebuild the data

The bundle in `data/` is a compact projection of the repo's corpus. Regenerate it after
any corpus change:

```bash
python explorer/build.py
```

## Run it locally

Serve the folder over http (opening the file directly blocks the data fetch):

```bash
python -m http.server -d explorer 8000
# then open http://localhost:8000
```

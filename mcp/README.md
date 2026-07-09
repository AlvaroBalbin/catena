# Catena MCP server

A fact-checked Catholic backend for any AI. It exposes the corpus and citation
graph over the Model Context Protocol so an assistant can ground a Catholic answer
in real, cited source - or be told plainly that the corpus does not contain it.

No third-party dependencies: stdio, newline-delimited JSON-RPC 2.0, stdlib only.

## Tools

| tool | what it returns |
|------|-----------------|
| `search(query, k)` | grounded, cited passages that answer a question - or `REFUSED` if the corpus has no answer |
| `get_article(citation)` | the full verbatim article at a citation, e.g. `ST I, q.2, a.3` |
| `lookup_verse(reference)` | every article that leans on a verse/chapter, e.g. `John 1:14` |
| `article_scripture(citation)` | the Scripture an article rests on |

The design intent is fidelity: `search` returns only real source and an explicit
`REFUSED` when it has nothing, so a well-behaved client cannot use Catena to invent
Church teaching.

## Prerequisites

Build the corpus and graph once:

```bash
python ingest/run.py --all
python ingest/build_graph.py
```

## Wire it into a client

**Claude Code:**

```bash
claude mcp add catena -- python /absolute/path/to/catena/mcp/server.py
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "catena": {
      "command": "python",
      "args": ["/absolute/path/to/catena/mcp/server.py"]
    }
  }
}
```

Any MCP client works; the server speaks standard stdio JSON-RPC. Verify it with
`python tests/test_mcp.py`.

"""
End-to-end smoke test of the MCP server over real stdio JSON-RPC.
Run: python tests/test_mcp.py   (build corpus + graph first)
"""

import json
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
SERVER = os.path.join(ROOT, "mcp", "server.py")


def rpc(id_, method, params=None):
    m = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        m["params"] = params
    return json.dumps(m)


def main() -> None:
    requests = [
        rpc(1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {}}),
        rpc(2, "tools/list"),
        rpc(3, "tools/call", {"name": "search", "arguments": {"query": "is sacred doctrine a science"}}),
        rpc(4, "tools/call", {"name": "search", "arguments": {"query": "how do I configure a kubernetes ingress"}}),
        rpc(5, "tools/call", {"name": "article_scripture", "arguments": {"citation": "ST I, q.2, a.3"}}),
        rpc(6, "tools/call", {"name": "lookup_verse", "arguments": {"reference": "John 1:14"}}),
        rpc(7, "tools/call", {"name": "get_article", "arguments": {"citation": "ST I, q.1, a.1"}}),
        rpc(8, "tools/call", {"name": "cross_references", "arguments": {"citation": "ST I, q.2, a.3"}}),
        rpc(9, "tools/call", {"name": "verse_fathers", "arguments": {"reference": "John 1:14"}}),
        rpc(10, "tools/call", {"name": "verse_fathers", "arguments": {"reference": "Genesis 1:1"}}),
    ]
    proc = subprocess.run(
        [sys.executable, SERVER],
        input="\n".join(requests) + "\n",
        capture_output=True, text=True, timeout=120,
    )
    responses = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        responses[msg.get("id")] = msg

    assert responses[1]["result"]["protocolVersion"] == "2024-11-05"
    assert responses[1]["result"]["serverInfo"]["name"] == "catena"

    names = {t["name"] for t in responses[2]["result"]["tools"]}
    assert names == {"search", "get_article", "lookup_verse", "verse_fathers",
                     "article_scripture", "cross_references"}, names

    grounded = responses[3]["result"]["content"][0]["text"]
    assert "ST I, q.1, a.2" in grounded and "grounded passage" in grounded

    refused = responses[4]["result"]["content"][0]["text"]
    assert refused.startswith("REFUSED"), refused

    assert "Exodus 3:14" in responses[5]["result"]["content"][0]["text"]
    assert "lean on John 1:14" in responses[6]["result"]["content"][0]["text"]

    article = responses[7]["result"]["content"][0]["text"]
    assert "Whether, besides philosophy" in article and "I answer that," in article

    xref = responses[8]["result"]["content"][0]["text"]
    assert "is cited by" in xref and "ST I, q.3, a.7" in xref

    fathers = responses[9]["result"]["content"][0]["text"]
    assert "Augustine" in fathers and "Catena Aurea, John 1:14" in fathers \
        and "made flesh" in fathers, fathers
    no_fathers = responses[10]["result"]["content"][0]["text"]
    assert no_fathers.startswith("REFUSED"), no_fathers  # Catena covers the Gospels only

    print("OK: MCP server grounds, refuses, serves articles, the Fathers, and walks the graph over stdio")


if __name__ == "__main__":
    main()

"""Minimal stdio MCP server for running experiments on Claude via `claude -p`.
Spec (JSON at $MOCK_SPEC): {"tools": [openai-style tool schemas], "rules": {tool: {"key": arg, "fail_value": v, "ok": str, "fail": str}}}
Every call is appended to $MOCK_LOG as JSON lines: {"name", "arguments"}."""
import json, os, sys

SPEC = json.load(open(os.environ["MOCK_SPEC"]))
LOG = os.environ["MOCK_LOG"]


def reply(i, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": i, "result": result}) + "\n"); sys.stdout.flush()


def respond(name, args):
    r = SPEC.get("rules", {}).get(name)
    if not r: return "ok"
    x = str(args.get(r["key"], "")).strip()
    return (r["fail"] if x == r.get("fail_value") else r["ok"]).replace("{x}", x)


for line in sys.stdin:
    try: m = json.loads(line)
    except Exception: continue
    meth, i = m.get("method"), m.get("id")
    if i is None: continue  # notification
    if meth == "initialize":
        reply(i, {"protocolVersion": m["params"].get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}}, "serverInfo": {"name": "svc", "version": "1.0"}})
    elif meth == "tools/list":
        reply(i, {"tools": [{"name": t["function"]["name"], "description": t["function"]["description"], "inputSchema": t["function"]["parameters"]} for t in SPEC["tools"]]})
    elif meth == "tools/call":
        name, args = m["params"]["name"], m["params"].get("arguments") or {}
        with open(LOG, "a") as f: f.write(json.dumps({"name": name, "arguments": args}) + "\n")
        reply(i, {"content": [{"type": "text", "text": respond(name, args)}]})
    else:
        reply(i, {})

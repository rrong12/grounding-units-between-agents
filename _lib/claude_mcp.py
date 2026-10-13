"""Run one agent episode on Claude through the local `claude -p` CLI (user's subscription; no API key), with the
experiment's tools served natively by mock_mcp.py. Isolation: no settings sources (no CLAUDE.md/hooks/plugins),
custom system prompt, built-in tools disabled, only the mock MCP server (canned responses, call log)."""
import json, os, subprocess, tempfile, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = Path(os.environ.get("CLAUDE_CLI_WORK", tempfile.gettempdir())) / "claude_cli_runs"
WORK.mkdir(parents=True, exist_ok=True)


def episode(system, prompt, tools=(), rules=None, model="sonnet", max_turns=25, timeout=600, server=None):
    """Returns {"text": final assistant text, "calls": [{"name","arguments"}], "error": str|None}.
    server: optional {"command", "args", "env"} replacing mock_mcp.py; "{LOG}" in env values becomes the call-log path."""
    rid = uuid.uuid4().hex[:12]; d = WORK / rid; d.mkdir()
    spec, log = d / "spec.json", d / "calls.jsonl"
    spec.write_text(json.dumps({"tools": list(tools), "rules": rules or {}}))
    cfg = d / "mcp.json"
    srv = {"command": "python3", "args": [str(HERE / "mock_mcp.py")], "env": {"MOCK_SPEC": str(spec), "MOCK_LOG": str(log)}}
    if server:
        srv = {"command": server["command"], "args": server["args"], "env": {k: v.replace("{LOG}", str(log)) for k, v in server["env"].items()}}
    cfg.write_text(json.dumps({"mcpServers": {"svc": srv}}))
    # Opt-in (HARNESS_NOTE env var): since ~2026-10-06 the subscription CLI injects the account email, today's date and an
    # environment section into every run, even with --system-prompt; the note tells the agent these are not about its principal.
    if os.environ.get("HARNESS_NOTE"): system = system + "\n\n" + os.environ["HARNESS_NOTE"]
    cmd = ["claude", "-p", "--setting-sources", "", "--model", model, "--system-prompt", system, "--tools", "",
           "--mcp-config", str(cfg), "--strict-mcp-config", "--allowedTools", "mcp__svc",
           "--max-turns", str(max_turns), "--output-format", "json", "--no-session-persistence"]
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=d)
        out = json.loads(p.stdout) if p.stdout.strip().startswith("{") else {}
        err = None if out and not out.get("is_error") else (out.get("result") or p.stderr or p.stdout)[:400]
        text = out.get("result") or ""; turns = out.get("num_turns")
    except Exception as e:
        text, err, turns = "", str(e)[:400], None
    calls = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
    for c in calls: c["name"] = c["name"].split("__")[-1]
    return {"text": text, "calls": calls, "error": err, "turns": turns}

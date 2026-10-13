"""Run one agent episode on OpenAI models through the local `codex exec` CLI (user's ChatGPT plan; no API key),
mirroring claude_mcp.episode: the experiment's tools are served by mock_mcp.py. Isolation: a private CODEX_HOME
(only auth.json linked), user config/rules ignored, custom base instructions, shell/patch/web tools disabled."""
import json, os, shutil, subprocess, tempfile, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = Path(os.environ.get("CODEX_CLI_WORK", tempfile.gettempdir())) / "codex_cli_runs"
WORK.mkdir(parents=True, exist_ok=True)
HOME = WORK / "_home"
HOME.mkdir(exist_ok=True)
if not (HOME / "auth.json").exists():
    os.symlink(Path.home() / ".codex" / "auth.json", HOME / "auth.json")
MODEL = "gpt-6.1-sol"


def episode(system, prompt, tools=(), rules=None, model=MODEL, effort="low", timeout=900, server=None, **_):
    """Returns {"text", "calls": [{"name","arguments"}], "error", "usage"}."""
    rid = uuid.uuid4().hex[:12]; d = WORK / rid; d.mkdir()
    spec, log, instr = d / "spec.json", d / "calls.jsonl", d / "instructions.md"
    spec.write_text(json.dumps({"tools": list(tools), "rules": rules or {}}))
    instr.write_text(system)
    off = ["apps", "browser_use", "browser_use_external", "code_mode", "computer_use", "goals", "image_generation",
           "multi_agent", "plugins", "shell_tool", "unified_exec", "view_image", "sleep_tool", "skill_search",
           "tool_suggest", "hooks", "memories", "realtime_conversation", "in_app_browser"]
    cfg = [f'model_instructions_file="{instr}"', f'model_reasoning_effort="{effort}"',
           'web_search="disabled"', 'project_doc_max_bytes=0', 'approval_policy="never"'] + [f"features.{f}=false" for f in off]
    if server:
        env_s = ", ".join(f'{k}="{v.replace("{LOG}", str(log))}"' for k, v in server["env"].items())
        cfg += [f'mcp_servers.svc.command="{server["command"]}"', "mcp_servers.svc.args=" + json.dumps(server["args"]),
                f"mcp_servers.svc.env={{{env_s}}}", 'mcp_servers.svc.default_tools_approval_mode="approve"', "mcp_servers.svc.startup_timeout_sec=180"]
    elif tools:
        cfg += [f'mcp_servers.svc.command="python3"', f'mcp_servers.svc.args=["{HERE / "mock_mcp.py"}"]',
                f'mcp_servers.svc.env={{MOCK_SPEC="{spec}", MOCK_LOG="{log}"}}',
                'mcp_servers.svc.default_tools_approval_mode="approve"']
    cmd = ["codex", "exec", "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
           "-s", "read-only", "-m", model, "-C", str(d)]
    for c in cfg: cmd += ["-c", c]
    env = dict(os.environ, CODEX_HOME=str(HOME))
    text, err, usage = "", None, None
    try:
        p = subprocess.run(cmd + ["-"], input=prompt, capture_output=True, text=True, timeout=timeout, env=env)
        for line in p.stdout.splitlines():
            try: e = json.loads(line)
            except Exception: continue
            t = e.get("type")
            it = e.get("item") or {}
            if t == "item.completed" and it.get("type") == "agent_message": text = it.get("text", "")
            elif t == "turn.completed": usage = e.get("usage")
            elif t in ("turn.failed", "error"): err = json.dumps(e)[:400]
        if not text and not err: err = (p.stderr or p.stdout)[-400:] or "empty"
    except Exception as e:
        err = str(e)[:400]
    calls = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
    shutil.rmtree(d, ignore_errors=True)
    return {"text": text, "calls": calls, "error": err, "usage": usage}

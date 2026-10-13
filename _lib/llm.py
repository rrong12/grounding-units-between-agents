"""Minimal OpenRouter client (stdlib only). Reads OPENROUTER key from repo-root .env without printing it."""
import json, os, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MODEL = "stealth/space-bunny-alpha"
_ROOT = Path(__file__).resolve().parents[2]


def _key():
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    for line in (_ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            if "OPENROUTER" in k.upper() or v.strip().strip('"\'').startswith("sk-or-"):
                return v.strip().strip('"\'')
    raise RuntimeError("no OpenRouter key in .env")


KEY = _key()
LAST_USAGE = {}


def chat(messages, tools=None, temperature=0.7, max_tokens=2000, reasoning=None, retries=5, model=MODEL, extra=None):
    """Returns the assistant message dict (content, tool_calls, reasoning)."""
    body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    if reasoning:
        body["reasoning"] = {"effort": reasoning}
    if extra:
        body.update(extra)
    data = json.dumps(body).encode()
    for i in range(retries + 3):
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions", data=data,
                headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                out = json.loads(r.read())
            if "choices" not in out:
                raise RuntimeError(str(out)[:300])
            global LAST_USAGE; LAST_USAGE = out.get("usage") or {}  # read by or_mcp for cost tracking
            msg = out["choices"][0]["message"]
            if not msg.get("content") and not msg.get("tool_calls"):
                raise RuntimeError("empty response")
            return msg
        except Exception as e:
            try:
                err = e.read().decode()[:300] if isinstance(e, urllib.error.HTTPError) else str(e)
            except Exception:
                err = str(e)
            rate_limited = "429" in err or "rate-limited" in err or "Rate limit" in err
            if i >= (retries + 3 if rate_limited else retries) - 1:
                return {"content": None, "error": err}
            time.sleep((15 if rate_limited else 3) * (i + 1))


def text(prompt, system=None, **kw):
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    return chat(msgs, **kw).get("content") or ""


def pmap(fn, items, workers=16):
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(fn, items))


def judge_json(prompt, **kw):
    """Ask for JSON; parse first {...} block."""
    kw.setdefault("temperature", 0)
    kw.setdefault("max_tokens", 8000)
    out = text(prompt + "\n\nRespond with only a JSON object.", **kw)
    s, e = out.find("{"), out.rfind("}")
    try:
        return json.loads(out[s:e + 1])
    except Exception:
        return {"_raw": out}


def run_agent(system, user, tools, handlers, max_steps=12, one_call_per_turn=False, **kw):
    """Simple tool loop. handlers: name -> fn(**args) -> str. Returns full message list.
    one_call_per_turn: only the first tool call of each turn is executed; the rest get an error asking to call again."""
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for _ in range(max_steps):
        m = chat(msgs, tools=tools, **kw)
        if m.get("error"):
            msgs.append({"role": "assistant", "content": f"[API ERROR] {m['error']}"})
            break
        msg = {"role": "assistant", "content": m.get("content") or ""}
        if m.get("tool_calls"):
            msg["tool_calls"] = m["tool_calls"]
        msgs.append(msg)
        if not m.get("tool_calls"):
            break
        for j, tc in enumerate(m["tool_calls"]):
            name = tc["function"]["name"]
            if one_call_per_turn and j > 0:
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": "Error: only one tool call per turn is supported. Call it again in a later turn."})
                continue
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
                res = handlers[name](**args) if name in handlers else f"Error: unknown tool {name}"
            except Exception as e:
                res = f"Error: {e}"
            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": str(res)})
    return msgs


def tool(_name, _desc, **props):
    """Shorthand tool schema: tool('read_file','Read a file', path='string')."""
    return {"type": "function", "function": {"name": _name, "description": _desc, "parameters": {
        "type": "object", "properties": {k: {"type": v} for k, v in props.items()}, "required": list(props)}}}


def transcript(msgs):
    out = []
    for m in msgs[1:]:
        if m["role"] == "tool":
            out.append(f"[TOOL RESULT] {m['content'][:800]}")
        else:
            calls = " ".join(f"<call {c['function']['name']}({c['function']['arguments']})>" for c in m.get("tool_calls", []))
            out.append(f"[{m['role'].upper()}] {m.get('content') or ''} {calls}")
    return "\n".join(out)

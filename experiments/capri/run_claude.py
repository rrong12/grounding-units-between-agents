"""CAPRI delegation on Claude via `claude -p` (native MCP tool for the acting agent). Same items/instructions/bands as run.py.
Difference: the CLI takes one prompt, so prior turns (CAPRI history; relay dialogue) are rendered as a transcript."""
import sys, json, os, random
sys.path.insert(0, os.path.abspath("../../_lib")); import llm, claude_mcp, codex_mcp, threading
from run import spec, RECV, INSTR, RESOLVE, SENDER, EXPLICIT, COUNTRY, conv_unit
T = llm.tool
def render(hist, label_user, label_asst):
    return "\n".join(f"{label_user if m['role'] == 'user' else label_asst}: {m['content']}" for m in hist)
def history(item):
    conv = item["conv"]; ks = [k for k in conv if conv[k]][:-1]
    return [{"role": "user" if k.startswith("user") else "assistant", "content": conv[k]} for k in ks]
def run(a):
    item, cond, k, same, model = a
    C = codex_mcp if model.startswith("gpt") else claude_mcp
    v, tgt, band = spec(item, same)
    sysR, tname, param = RECV[(item["concept"], tgt)]
    tool = T(tname, f"{tname.replace('_', ' ')}; {param} is a number", **{param: "number"})
    instr = INSTR[item["concept"]].format(v=v)
    ok = lambda args: band[0] <= float(args.get(param, -1e9)) <= band[1]
    loc = COUNTRY.get(item["culture"], item["culture"])
    H = render(history(item), "Principal", "You")
    base = {"file": item["file"], "concept": item["concept"], "culture": item["culture"], "cond": cond, "same": same, "model": model}
    if cond == "direct":
        s = sysR.replace("You are the", "You are a personal assistant with access to the") + " Act on your principal's requests."
        r = C.episode(s, f"[Earlier conversation with your principal]\n{H}\n\n[New message from your principal]\n{instr}", [tool], model=model, max_turns=4)
        if r["error"]: return dict(base, error=r["error"])
        got = r["calls"][0]["arguments"] if r["calls"] else {}
        first, turns = None, 0 if got else 1
    else:
        sb = sysR + f" Use {tname}({param}) to act."
        if cond in ("card", "card+resolver", "explicit+card+resolver"): sb += f"\n\n[Agent card of the counterpart] principal_locale: {loc}"
        if cond.endswith("card+resolver"): sb += "\n\n" + RESOLVE
        sa = SENDER + (EXPLICIT if cond.startswith("explicit") else "") + " Reply with only the message text to send to the other agent."
        dlg, got, turns, first = [], {}, 0, None
        for _ in range(4):
            pa = f"[Earlier conversation with your principal]\n{H}\n\nPrincipal: {instr}\n\n(You are connected to the other business's agent.)\n" + (f"[Dialogue with the other agent so far]\n{render(dlg, 'Other agent', 'You')}\n\n" if dlg else "") + "Write your next message to the other agent."
            ra = C.episode(sa, pa, model=model, max_turns=2)
            if ra["error"]: return dict(base, error=ra["error"])
            am = ra["text"].strip(); first = first if first is not None else am
            dlg.append({"role": "assistant", "content": am})
            pb = "[Conversation with the other agent]\n" + render(dlg, "You", "Other agent").replace("You:", "TMP:").replace("Other agent:", "You:").replace("TMP:", "Other agent:") + "\n\nRespond to the other agent, or use your tool to act."
            rb = C.episode(sb, pb, [tool], model=model, max_turns=4)
            if rb["error"]: return dict(base, error=rb["error"])
            if rb["calls"]:
                got = rb["calls"][0]["arguments"]; break
            turns += 1; dlg.append({"role": "user", "content": rb["text"].strip()})
    try: good = bool(got) and ok(got)
    except Exception: good = False
    return dict(base, error=None, kind="implicit", correct=good, acted=bool(got), asked=turns > 0, silent_wrong=bool(got) and not good and turns == 0, args=got, sender_first=(first or "")[:400])
LOCK = threading.Lock()
def logged(a):
    r = run(a)
    with LOCK, open(OUT, "a") as fh: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return r
if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else "sonnet"
    step = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    conds = sys.argv[3].split(",") if len(sys.argv) > 3 else ["direct", "none", "card+resolver", "explicit+card+resolver"]
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    OUT = f"results_frontier_{model}{os.environ.get('RESULTS_TAG', '')}.jsonl"
    S = [s for s in json.load(open("sample.json")) if s["kind"] == "implicit" and not (s["concept"] == "price" and s["culture"] == "Iran")][::step]
    jobs = [(s, c, 0, False, model) for s in S for c in conds]
    jobs += [(s, c, 0, True, model) for s in S[::3] for c in ["none", "explicit+card+resolver"] if c in conds and not (s["concept"] == "price" and conv_unit("price", s["culture"]) not in ("USD", "EUR"))]
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            x = json.loads(l)
            if not x.get("error"): done.add((x["file"], x["cond"], x["same"]))
    jobs = [j for j in jobs if (j[0]["file"], j[1], j[3]) not in done]
    random.Random(0).shuffle(jobs)
    print(model, len(jobs), "jobs", flush=True)
    res = llm.pmap(logged, jobs, workers=workers)
    print("errors:", sum(bool(r.get("error")) for r in res), "of", len(res), flush=True)

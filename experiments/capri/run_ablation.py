"""Ablations on CAPRI (conditions requested in internal reviews). Conditions are '+'-joined tokens:
  explicit  sender told to infer the principal's locale and never send bare numbers
  card      receiver sees the ORACLE locale (CAPRI culture) in the counterpart's agent card
  inferred  receiver's card holds the locale the SENDER model inferred from the history (non-oracle)
  resolver  receiver told to resolve convention-dependent expressions in the sender's convention
  generic   generic caution on both sides, no mention of units/locales (prompt-length control)
  desc      tool parameter named 'value', unit stated only in the tool description
  hybrid    sender states units + a confidence per quantity; receiver asks when a unit is missing or confidence is low
  typed     sender must send JSON {request, quantities:[{value, unit}]} with a mandatory unit (format-enforced explicitness)
  inject:K  counterfactual: the sender's message is replaced by a fixed template with K in {bare, own, wrong, hedged};
            the receiver answers once (review 2 W3: interventional test of the sender-message effect)
  none      plain relay;  direct = single agent holds the tool
Sender and receiver models can differ. Usage:
  python run_ablation.py SENDER RECEIVER CONDS [--amb] [--step K] [--same] [--workers W]
Appends to results_ablation.jsonl (resumable)."""
import sys, json, os, random, threading, argparse
sys.argv, _argv = sys.argv[:1], sys.argv
sys.path.insert(0, os.path.abspath("../../_lib")); import llm, claude_mcp, codex_mcp
from run import spec, RECV, INSTR, RESOLVE, SENDER, EXPLICIT, COUNTRY, conv_unit
from run_claude import render, history
T = llm.tool
OUT = f"results_ablation{os.environ.get('RESULTS_TAG', '')}.jsonl"; LOCK = threading.Lock()
GEN_S = " Be careful to communicate your principal's request clearly and accurately."
GEN_R = "\n\nRequests from other agents may be ambiguous. Make sure you interpret them correctly before acting."
HYB_S = (" State every quantity with an explicit unit or currency as your principal means it, followed by your confidence in that "
         "reading in brackets, e.g. '(confidence: high)' or '(confidence: low)'.")
HYB_R = "\n\nIf a quantity in the other agent's request has no unit, or the sender marks its confidence as low, ask the other agent before acting."
TYPED_S = (' Your message must be ONLY a JSON object: {"request": "<what to do>", "quantities": [{"value": <number>, "unit": "<unit or ISO currency code '
           'as your principal means it>"}]}. The unit field is mandatory for every quantity.')
UNAME = {"C": "°C", "F": "°F", "kmh": "km/h", "mph": "mph", "km": "km", "mi": "miles", "sqm": "square metres", "sqft": "square feet"}
ACT = {"temperature": "please set the room thermostat for my principal's arrival tonight to {q}",
       "speed": "please set the speed alert on my principal's rental car to {q}",
       "distance": "please only show my principal hotels within {q} of the conference venue",
       "size": "please only show my principal apartments of at least {q}",
       "price": "please note that my principal's maximum budget for the chair is {q}"}
B = lambda m: codex_mcp if m.startswith("gpt") else claude_mcp
AMB = {"speed", "distance", "price"}


def infer_locale(sm, H):
    r = B(sm).episode("You are a careful assistant.", f"[Conversation between a user and their assistant]\n{H}\n\nIn which country does the user most likely live? Answer with only the country name.", model=sm, max_turns=1)
    return (r["text"] or "unknown").strip().split("\n")[0][:60]


def run(a):
    item, cond, same, sm, rm = a
    tok = set(cond.split("+"))
    v, tgt, band = spec(item, same)
    sysR, tname, param = RECV[(item["concept"], tgt)]
    if "desc" in tok:
        unit = param.split("_")[-1] if "_" in param else param
        tool = T(tname, f"{tname.replace('_', ' ')}. The value is in {unit}.", value="number"); key = "value"
    else:
        tool = T(tname, f"{tname.replace('_', ' ')}; {param} is a number", **{param: "number"}); key = param
    instr = INSTR[item["concept"]].format(v=v)
    ok = lambda args: band[0] <= float(args.get(key, -1e9)) <= band[1]
    loc = COUNTRY.get(item["culture"], item["culture"])
    H = render(history(item), "Principal", "You")
    base = {"file": item["file"], "concept": item["concept"], "culture": item["culture"], "cond": cond, "same": same, "sender": sm, "receiver": rm}
    inferred = None
    if "direct" in tok:
        s = sysR.replace("You are the", "You are a personal assistant with access to the") + " Act on your principal's requests." + (GEN_R if "generic" in tok else "")
        r = B(rm).episode(s, f"[Earlier conversation with your principal]\n{H}\n\n[New message from your principal]\n{instr}", [tool], model=rm, max_turns=4)
        if r["error"]: return dict(base, error=r["error"])
        got = r["calls"][0]["arguments"] if r["calls"] else {}
        first, turns = None, 0 if got else 1
    elif cond.startswith("inject:"):
        kind = cond.split(":")[1]; own = conv_unit(item["concept"], item["culture"])
        nm = lambda u: UNAME.get(u, u)
        q = {"bare": f"{v:g}", "own": f"{v:g} {nm(own)}", "wrong": f"{v:g} {nm(tgt)}", "hedged": f"{v:g} (I'm not sure whether that is {nm(own)} or {nm(tgt)})"}[kind]
        first = "Hello, I'm writing on behalf of my principal: " + ACT[item["concept"]].format(q=q) + "."
        sb = sysR + f" Use {tname} to act."
        rb = B(rm).episode(sb, f"[Conversation with the other agent]\nOther agent: {first}\n\nRespond to the other agent, or use your tool to act.", [tool], model=rm, max_turns=4)
        if rb["error"]: return dict(base, error=rb["error"])
        got = rb["calls"][0]["arguments"] if rb["calls"] else {}; turns = 0 if got else 1
    else:
        sb = sysR + f" Use {tname} to act."
        if "card" in tok: sb += f"\n\n[Agent card of the counterpart] principal_locale: {loc}"
        if "inferred" in tok:
            inferred = infer_locale(sm, H); sb += f"\n\n[Agent card of the counterpart] principal_locale: {inferred}"
        if "resolver" in tok: sb += "\n\n" + RESOLVE
        if "generic" in tok: sb += GEN_R
        if "hybrid" in tok: sb += HYB_R
        sa = SENDER + (EXPLICIT if "explicit" in tok else "") + (GEN_S if "generic" in tok else "") + (HYB_S if "hybrid" in tok else "") + \
             (TYPED_S if "typed" in tok else " Reply with only the message text to send to the other agent.")
        dlg, got, turns, first = [], {}, 0, None
        for _ in range(4):
            pa = f"[Earlier conversation with your principal]\n{H}\n\nPrincipal: {instr}\n\n(You are connected to the other business's agent.)\n" + (f"[Dialogue with the other agent so far]\n{render(dlg, 'Other agent', 'You')}\n\n" if dlg else "") + "Write your next message to the other agent."
            ra = B(sm).episode(sa, pa, model=sm, max_turns=2)
            if ra["error"]: return dict(base, error=ra["error"])
            am = ra["text"].strip(); first = first if first is not None else am
            dlg.append({"role": "assistant", "content": am})
            pb = "[Conversation with the other agent]\n" + render(dlg, "You", "Other agent").replace("You:", "TMP:").replace("Other agent:", "You:").replace("TMP:", "Other agent:") + "\n\nRespond to the other agent, or use your tool to act."
            rb = B(rm).episode(sb, pb, [tool], model=rm, max_turns=4)
            if rb["error"]: return dict(base, error=rb["error"])
            if rb["calls"]:
                got = rb["calls"][0]["arguments"]; break
            turns += 1; dlg.append({"role": "user", "content": rb["text"].strip()})
    try: good = bool(got) and ok(got)
    except Exception: good = False
    return dict(base, error=None, correct=good, acted=bool(got), asked=turns > 0, silent_wrong=bool(got) and not good and turns == 0,
                args=got, sender_first=(first or "")[:400], inferred_locale=inferred,
                inferred_ok=(inferred is not None and loc.lower() in inferred.lower()) if inferred else None)


def logged(a):
    r = run(a)
    with LOCK, open(OUT, "a") as fh: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("sender"); ap.add_argument("receiver"); ap.add_argument("conds")
    ap.add_argument("--amb", action="store_true"); ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--same", action="store_true", help="same-convention controls instead of cross-convention")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(_argv[1:])
    S = [s for s in json.load(open("sample.json")) if s["kind"] == "implicit" and not (s["concept"] == "price" and s["culture"] == "Iran")]
    if a.amb: S = [s for s in S if s["concept"] in AMB]
    S = S[::a.step]
    if a.same: S = [s for s in S if not (s["concept"] == "price" and conv_unit("price", s["culture"]) not in ("USD", "EUR"))]
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            x = json.loads(l)
            if not x.get("error"): done.add((x["file"], x["cond"], x["same"], x["sender"], x["receiver"]))
    jobs = [(s, c, a.same, a.sender, a.receiver) for s in S for c in a.conds.split(",") if (s["file"], c, a.same, a.sender, a.receiver) not in done]
    random.Random(0).shuffle(jobs)
    print(a.sender, "->", a.receiver, a.conds, "same" if a.same else "", len(jobs), "jobs", flush=True)
    res = llm.pmap(logged, jobs, workers=a.workers)
    print("errors:", sum(bool(r.get("error")) for r in res), "of", len(res), flush=True)

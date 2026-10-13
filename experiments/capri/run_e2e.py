"""End-to-end delegation with a simulated principal (EXPERIMENT_PLAN.md D and E). The sender can consult its principal
(ASK_PRINCIPAL); the receiver's questions reach the sender, which answers or escalates. The run_ablation.py harness is left
untouched; this file reuses its prompts. Conditions are '+'-joined tokens:
  baselines  none | explicit (CAPRI's explicit prompting) | pcot (CAPRI's Pragmatic CoT on the sender) | typed (JSON with a
             mandatory unit) | selfunc (receiver must ask when its own request uncertainty >= 0.5, Matsnev 2026) |
             hybrid, inferred, card, resolver (as in run_ablation.py)
  method     ground   sender quotes the cue, then sends value + unit + BCP 47 locale tag + confidence; asks its principal when unsure
             xcheck   receiver checks the unit against the stated locale and the value against plausibility; asks on conflict
             readback receiver must first restate the converted value (no tool on that turn); sender confirms or corrects
  control    stated   the principal states the unit in the instruction ("300000 South Korean won"): conversion, not inference
The simulated principal is deterministic: it knows its value and unit and answers only questions about the unit or meaning.
Usage: python run_e2e.py SENDER RECEIVER CONDS --split dev|heldout [--step K] [--same] [--workers W]
Appends to results_e2e.jsonl (resumable)."""
import sys, json, os, re, random, threading, argparse
sys.argv, _argv = sys.argv[:1], sys.argv
sys.path.insert(0, os.path.abspath("../../_lib")); import llm, claude_mcp, codex_mcp
from run import spec, RECV, INSTR, RESOLVE, SENDER, EXPLICIT, COUNTRY, conv_unit
from run_claude import render, history
from run_ablation import HYB_S, HYB_R, TYPED_S, infer_locale, AMB
T = llm.tool
OUT = os.environ.get("E2E_OUT", f"results_e2e{os.environ.get('RESULTS_TAG', '')}.jsonl"); LOCK = threading.Lock()
B = lambda m: codex_mcp if m.startswith("gpt") else claude_mcp

UNIT_NL = {"C": "degrees Celsius", "F": "degrees Fahrenheit", "kmh": "km/h", "mph": "mph", "km": "kilometres", "mi": "miles",
           "sqm": "square metres", "sqft": "square feet", "CNY": "Chinese yuan", "EUR": "euros", "GBP": "British pounds",
           "KRW": "South Korean won", "JPY": "Japanese yen", "INR": "Indian rupees", "BRL": "Brazilian reais",
           "ILS": "Israeli shekels", "USD": "US dollars"}
PRINCIPAL_S = " If you need to check something with your principal first, reply with only a line starting with 'ASK_PRINCIPAL:' followed by your question."
PLAIN_FMT = " Reply with only the message text to send to the other agent."
# "write your reasoning" trips Opus 5.5's reasoning-extraction safeguard (2026-10-08), so the scratch part is a short NOTES line
REASONED = " First write a short note after 'NOTES:', then the message after 'MESSAGE:'. Only the text after 'MESSAGE:' is sent."
PCOT_S = " Before writing, work out your principal's background; your note must end with 'This user is from [country].' or '[unknown]'."
GROUND_S = (" Before writing, work out from your conversation with your principal which country they most likely live in; in your note, quote "
            "the cue(s) that show it. In your message, state every quantity as a value with the unit or currency your principal means, give your "
            "principal's locale as a BCP 47 tag (for example ko-KR), and give your confidence that you have the unit right (high or low). "
            "If you are not confident which unit your principal means, ask your principal before writing.")
RB_S = " If the other agent restates a value back to you, check it against what your principal meant and confirm or correct it."
XCHECK_R = ("\n\nBefore acting, cross-check each quantity in the other agent's request: if no unit is given, if its unit or currency does not "
            "fit the sender's stated locale, or if the value would be implausible for this request, ask the other agent before acting.")
SELFUNC_R = ("\n\nBefore acting, rate your uncertainty about what the other agent's request means: u = 0 if it fully specifies every "
             "parameter, u = 0.5 if it leaves open a choice the sender likely has a preference about, u = 1 if critical details are missing. "
             "If u >= 0.5 you MUST ask the other agent a clarifying question instead of acting.")
RB_TURN = ("Before acting, restate to the other agent exactly what you will enter into your system (the value in your system's unit) and "
           "what it corresponds to in their terms, and ask them to confirm. Do not act yet.")
UNIT_Q = re.compile(r"\bunits?\b|currenc|\bkm\b|kilomet|\bmiles?\b|\bmph\b|per hour|km/h|kph|dollar|\beuros?\b|\bwon\b|\byen\b|yuan|rupee|"
                    r"\breais?\b|\breal\b|shekel|pound|celsius|fahrenheit|square (feet|met)|metric|imperial|[$€£¥₹₩₪]", re.I)
# the task is underspecified on purpose (no booking references etc.); without this both agents loop on logistics
LOGI_S = " The other business already has your principal's booking and account details, so you never need to supply reference numbers or contact details."
LOGI_R = " The other agent is already authenticated as your customer's representative and your system has the customer's booking, so you never need reference numbers or contact details."
MAX_ESC, MAX_ROUNDS = 2, 4


def principal_answer(q, v, own):
    """Answers only questions about the unit, or about what the number means (the number is quoted with a unit/meaning word)."""
    num = re.escape(f"{v:g}"), re.escape(f"{v:,.0f}") if v >= 1000 else re.escape(f"{v:g}")
    about_number = any(re.search(n + r".{0,40}\b(mean|meant|refer|in what|which)\b|\b(mean|meant|refer)\b.{0,40}" + n, q, re.I) for n in num)
    if UNIT_Q.search(q) or about_number: return f"I mean {v:g} {UNIT_NL[own]}."
    return "Please just go ahead with what I told you; the company already has my booking details."


def message_part(text):
    return text.rsplit("MESSAGE:", 1)[1].strip() if "MESSAGE:" in text else text.strip()


def run(a):
    item, cond, same, sm, rm, split, rep = a
    tok = set(cond.split("+"))
    v, tgt, band = spec(item, same)
    own = tgt if same else conv_unit(item["concept"], item["culture"])
    sysR, tname, param = RECV[(item["concept"], tgt)]
    tool = T(tname, f"{tname.replace('_', ' ')}; {param} is a number", **{param: "number"})
    instr = INSTR[item["concept"]].format(v=f"{v:g} {UNIT_NL[own]}" if "stated" in tok else v)
    ok = lambda args: band[0] <= float(args.get(param, -1e9)) <= band[1]
    loc = COUNTRY.get(item["culture"], item["culture"])
    H = render(history(item), "Principal", "You")
    base = {"file": item["file"], "concept": item["concept"], "culture": item["culture"], "cond": cond, "same": same,
            "sender": sm, "receiver": rm, "split": split, "rep": rep}
    sb = sysR + LOGI_R + f" Use {tname} to act."
    inferred = None
    if "card" in tok: sb += f"\n\n[Agent card of the counterpart] principal_locale: {loc}"
    if "inferred" in tok:
        inferred = infer_locale(sm, H); sb += f"\n\n[Agent card of the counterpart] principal_locale: {inferred}"
    if "resolver" in tok: sb += "\n\n" + RESOLVE
    if "hybrid" in tok: sb += HYB_R
    if "xcheck" in tok: sb += XCHECK_R
    if "selfunc" in tok: sb += SELFUNC_R
    reasoned = bool(tok & {"ground", "pcot"})
    sa = SENDER + LOGI_S + (EXPLICIT if "explicit" in tok else "") + (HYB_S if "hybrid" in tok else "") + (GROUND_S if "ground" in tok else "") + \
         (PCOT_S if "pcot" in tok else "") + (RB_S if "readback" in tok else "") + \
         (TYPED_S if "typed" in tok else REASONED if reasoned else PLAIN_FMT) + PRINCIPAL_S
    dlg, pqa, log = [], [], []
    got, asks, esc, first, rb_done = {}, 0, 0, None, "readback" not in tok

    def sender_turn():
        nonlocal esc
        while True:
            qa = "".join(f"You (to your principal): {q}\nPrincipal: {ans}\n" for q, ans in pqa)
            pa = (f"[Earlier conversation with your principal]\n{H}\n\nPrincipal: {instr}\n{qa}"
                  + ("(Your principal is not available any more.)\n" if esc >= MAX_ESC else "")
                  + "\n(You are connected to the other business's agent.)\n"
                  + (f"[Dialogue with the other agent so far]\n{render(dlg, 'Other agent', 'You')}\n\n" if dlg else "")
                  + "Write your next message to the other agent.")
            r = B(sm).episode(sa, pa, model=sm, max_turns=2)
            if r["error"]: return None, r["error"]
            text = r["text"].strip(); m = re.search(r"ASK_PRINCIPAL:\s*(.+)", text, re.S)
            if m and esc < MAX_ESC:
                q = m.group(1).strip()[:400]; ans = principal_answer(q, v, own)
                pqa.append((q, ans)); esc += 1; log.append(("sender->principal", q)); log.append(("principal", ans))
                continue
            msg = message_part(re.sub(r"ASK_PRINCIPAL:.*", "", text, flags=re.S)) or text
            log.append(("sender", msg)); return msg, None

    def receiver_view():
        return "[Conversation with the other agent]\n" + render(dlg, "You", "Other agent").replace("You:", "TMP:").replace(
            "Other agent:", "You:").replace("TMP:", "Other agent:")

    rounds = 0
    while rounds < MAX_ROUNDS:
        msg, err = sender_turn()
        if err: return dict(base, error=err)
        first = first if first is not None else msg
        dlg.append({"role": "assistant", "content": msg})
        if not rb_done:
            rb = B(rm).episode(sb, receiver_view() + "\n\n" + RB_TURN, model=rm, max_turns=1)
            if rb["error"]: return dict(base, error=rb["error"])
            rb_done = True; dlg.append({"role": "user", "content": rb["text"].strip()}); log.append(("receiver(readback)", rb["text"].strip()))
            continue
        rb = B(rm).episode(sb, receiver_view() + "\n\nRespond to the other agent, or use your tool to act.", [tool], model=rm, max_turns=4)
        if rb["error"]: return dict(base, error=rb["error"])
        if rb["calls"]:
            got = rb["calls"][0]["arguments"]; log.append(("receiver(tool)", json.dumps(got))); break
        asks += 1; rounds += 1; dlg.append({"role": "user", "content": rb["text"].strip()}); log.append(("receiver", rb["text"].strip()))
    try: good = bool(got) and ok(got)
    except Exception: good = False
    outcome = ("no_action" if not got else ("correct" if good else "silent_wrong") if asks == 0 else
               ("asked_correct" if good else "asked_wrong"))
    return dict(base, error=None, correct=good, acted=bool(got), asks=asks, asked=asks > 0, escalations=esc,
                readback="readback" in tok, silent_wrong=outcome == "silent_wrong", outcome=outcome, args=got,
                sender_first=(first or "")[:600], inferred_locale=inferred,
                inferred_ok=(loc.lower() in inferred.lower()) if inferred else None, transcript=[(w, t[:600]) for w, t in log])


def logged(a):
    r = run(a)
    with LOCK, open(OUT, "a") as fh: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return r


def items(split, step, same):
    if split == "dev":
        S = [s for s in json.load(open("sample.json")) if s["kind"] == "implicit" and s["concept"] in AMB]
    else:
        S = json.load(open("heldout.json"))
    S = [s for s in S if not (s["concept"] == "price" and s["culture"] == "Iran") and not (s["concept"] == "distance" and s["culture"] == "UK")]
    S = S[::step]
    if same: S = [s for s in S if not (s["concept"] == "price" and conv_unit("price", s["culture"]) not in ("USD", "EUR"))]
    return S


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("sender"); ap.add_argument("receiver"); ap.add_argument("conds")
    ap.add_argument("--split", default="dev", choices=["dev", "heldout"]); ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--same", action="store_true"); ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="smoke test: only the first N items")
    ap.add_argument("--rep", type=int, default=0, help="repeat index (reliability re-runs of the same items)")
    a = ap.parse_args(_argv[1:])
    S = items(a.split, a.step, a.same)
    if a.limit: S = S[:a.limit]
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            x = json.loads(l)
            if not x.get("error"): done.add((x["file"], x["cond"], x["same"], x["sender"], x["receiver"], x.get("rep", 0)))
    jobs = [(s, c, a.same, a.sender, a.receiver, a.split, a.rep) for s in S for c in a.conds.split(",")
            if (s["file"], c, a.same, a.sender, a.receiver, a.rep) not in done]
    random.Random(0).shuffle(jobs)
    print(a.sender, "->", a.receiver, a.conds, a.split, "same" if a.same else "", len(jobs), "jobs", flush=True)
    res = llm.pmap(logged, jobs, workers=a.workers)
    print("errors:", sum(bool(r.get("error")) for r in res), "of", len(res), flush=True)

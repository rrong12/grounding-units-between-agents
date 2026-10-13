"""Sender-only probe (EXPERIMENT_PLAN.md D). With no counterpart, what does the sender think its principal's bare number means?
One call per item; the instruction is the same bare-number request the relay uses. Variants (system prompt):
  neutral          a plain personal assistant, no mention of other businesses
  sender           the relay's SENDER prompt
  sender+explicit  SENDER + EXPLICIT ("the other agent may be in a different country ... state every quantity with a unit")
Coding: own (principal's unit), wrong (another unit), hedged (both), bare (no unit).
Usage: python run_probe.py MODEL VARIANTS [--step K] [--workers W]; appends to results_probe.jsonl (resumable)."""
import sys, json, os, re, random, threading, argparse
sys.argv, _argv = sys.argv[:1], sys.argv
sys.path.insert(0, os.path.abspath("../../_lib")); import llm, claude_mcp, codex_mcp
from run import INSTR, SENDER, EXPLICIT, spec, conv_unit
from run_claude import render, history
OUT = os.environ.get("PROBE_OUT", f"results_probe{os.environ.get('RESULTS_TAG', '')}.jsonl"); LOCK = threading.Lock()
B = lambda m: codex_mcp if m.startswith("gpt") else claude_mcp
SYS = {"neutral": "You are your principal's personal assistant.", "sender": SENDER, "sender+explicit": SENDER + EXPLICIT}
Q = ("Before doing anything else: what exact quantity does your principal mean in their last message? "
     "Reply with only the number and its unit or currency.")
# same unit patterns as analyze_frontier.py
PAT = {"kmh": r"km/h|kph|kmh|kilomet", "mph": r"mph|miles per hour", "km": r"\bkm\b|kilomet", "mi": r"\bmi\b|\bmiles?\b",
       "CNY": r"yuan|RMB|CNY|元", "EUR": r"€|euro|EUR", "GBP": r"£|pound|GBP", "KRW": r"₩|\bwon\b|KRW", "JPY": r"\byen\b|JPY|円",
       "INR": r"₹|rupee|INR|\bRs\.?", "BRL": r"R\$|rea(l|is)\b|BRL", "ILS": r"₪|shekel|NIS|ILS", "USD": r"(?<!R)\$|dollar|USD"}
UNITS = {"speed": ["kmh", "mph"], "distance": ["km", "mi"], "price": ["CNY", "EUR", "GBP", "KRW", "JPY", "INR", "BRL", "ILS", "USD"]}


DOUBT = re.compile(r"not specified|unspecified|didn'?t specify|did not specify|not sure|unsure|unclear|don'?t know|cannot tell|can'?t tell|ambiguous", re.I)


def code(text, concept, own):
    if DOUBT.search(text): return "doubt"  # says it doesn't know the unit (may list candidates)
    hits = {u for u in UNITS[concept] if re.search(PAT[u], text, 0 if u.isupper() else re.I)}
    if concept == "price" and "¥" in text: hits |= {"CNY"} if own == "CNY" else {"JPY"}  # ¥ is both yuan and yen
    return "bare" if not hits else "hedged" if len(hits) > 1 else "own" if own in hits else "wrong"


def run(a):
    item, var, m = a
    v, _, _ = spec(item)
    own = conv_unit(item["concept"], item["culture"])
    H = render(history(item), "Principal", "You")
    r = B(m).episode(SYS[var], f"[Earlier conversation with your principal]\n{H}\n\nPrincipal: {INSTR[item['concept']].format(v=v)}\n\n{Q}", model=m, max_turns=1)
    base = {"file": item["file"], "concept": item["concept"], "culture": item["culture"], "variant": var, "model": m}
    if r["error"]: return dict(base, error=r["error"])
    t = (r["text"] or "").strip()
    return dict(base, error=None, answer=t[:300], own=own, code=code(t, item["concept"], own))


def logged(a):
    r = run(a)
    with LOCK, open(OUT, "a") as fh: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("model"); ap.add_argument("variants")
    ap.add_argument("--step", type=int, default=1); ap.add_argument("--workers", type=int, default=4); ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args(_argv[1:])
    S = [s for s in json.load(open("sample.json")) if s["kind"] == "implicit" and s["concept"] in UNITS and not (s["concept"] == "price" and s["culture"] == "Iran")][::a.step]
    if a.limit: S = S[:a.limit]
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            x = json.loads(l)
            if not x.get("error"): done.add((x["file"], x["variant"], x["model"]))
    jobs = [(s, v, a.model) for s in S for v in a.variants.split(",") if (s["file"], v, a.model) not in done]
    random.Random(0).shuffle(jobs)
    print(a.model, a.variants, len(jobs), "jobs", flush=True)
    res = llm.pmap(logged, jobs, workers=a.workers)
    print("errors:", sum(bool(r.get("error")) for r in res), "of", len(res), flush=True)

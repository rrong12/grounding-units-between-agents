"""Summarise the CAPRI frontier runs (results_frontier_*.jsonl, results_claude_sonnet.json, results_ablation.jsonl).
Metrics: correct, silent wrong, asked, safe = correct or asked (review 1 W3). 95% CIs from a bootstrap clustered by
culture x concept (W5). Paired McNemar tests between conditions on the same items. Sender first-message coding (W9)."""
import json, glob, random, collections, re, math, sys
sys.argv = sys.argv[:1]
from run import conv_unit
AMB = {"speed", "distance", "price"}
PAT = {"C": r"°\s?C|celsius", "F": r"°\s?F|fahrenheit", "kmh": r"km/h|kph|kmh|kilomet", "mph": r"mph|miles per hour",
       "km": r"\bkm\b|kilomet", "mi": r"\bmi\b|\bmiles?\b", "sqm": r"m²|\bm2\b|sq\.?\s?m\b|square met|sqm", "sqft": r"sq\.?\s?ft|square f|ft²|sqft",
       "CNY": r"yuan|RMB|CNY|元", "EUR": r"€|euro|EUR", "GBP": r"£|pound|GBP", "KRW": r"₩|\bwon\b|KRW", "JPY": r"\byen\b|JPY|円",
       "INR": r"₹|rupee|INR|\bRs\.?", "BRL": r"R\$|rea(l|is)\b|BRL", "ILS": r"₪|shekel|NIS|ILS", "USD": r"(?<!R)\$|dollar|USD"}
UNITS = {"temperature": ["C", "F"], "speed": ["kmh", "mph"], "distance": ["km", "mi"], "size": ["sqm", "sqft"],
         "price": ["CNY", "EUR", "GBP", "KRW", "JPY", "INR", "BRL", "ILS", "USD"]}


def sender_unit(r):
    t = r.get("sender_first") or ""; own = conv_unit(r["concept"], r["culture"])
    hits = {u for u in UNITS[r["concept"]] if re.search(PAT[u], t, 0 if u.isupper() else re.I)}
    return "bare" if not hits else "hedged" if len(hits) > 1 else "own" if own in hits else "wrong"


def cci(rows, f, B=2000):
    """mean and 95% CI, bootstrap over culture x concept clusters"""
    if not rows: return (float("nan"),) * 3
    cl = collections.defaultdict(list)
    for r in rows: cl[(r["culture"], r["concept"])].append(float(f(r)))
    keys = list(cl); rng = random.Random(0); m = sum(sum(v) for v in cl.values()) / len(rows); bs = []
    for _ in range(B):
        s = [cl[rng.choice(keys)] for _ in keys]; n = sum(len(x) for x in s)
        bs.append(sum(sum(x) for x in s) / n)
    bs.sort(); return m, bs[int(.025 * B)], bs[int(.975 * B)]


def fmt(rows, f): m, lo, hi = cci(rows, f); return f"{m:.2f} [{lo:.2f},{hi:.2f}]"
safe = lambda r: r["correct"] or r["asked"]


def mcnemar(R, c1, c2, sub):
    a = {r["file"]: r["correct"] for r in R if r["cond"] == c1 and not r["same"] and sub(r)}
    b = {r["file"]: r["correct"] for r in R if r["cond"] == c2 and not r["same"] and sub(r)}
    k = [f for f in a if f in b]; n01 = sum(not a[f] and b[f] for f in k); n10 = sum(a[f] and not b[f] for f in k)
    if n01 + n10 == 0: return f"{c1} vs {c2}: no discordant pairs (n={len(k)})"
    x = min(n01, n10); n = n01 + n10
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(x + 1)) / 2 ** n)  # exact binomial
    return f"{c1} -> {c2}: +{n01} / -{n10} of {len(k)} paired items, exact p={p:.3g}"


def table(R, conds, title):
    print(f"\n== {title}  (n ok={len(R)})")
    print(f"  {'condition':30s} {'AMBIGUOUS correct':22s} {'silent wrong':22s} {'safe(correct|asked)':22s} n   | all items correct")
    for c in conds:
        v = [r for r in R if r["cond"] == c and not r["same"]]
        if not v: continue
        a = [r for r in v if r["concept"] in AMB]
        print(f"  {c:30s} {fmt(a, lambda r: r['correct']):22s} {fmt(a, lambda r: r['silent_wrong']):22s} {fmt(a, safe):22s} {len(a):3d} | {fmt(v, lambda r: r['correct'])} n={len(v)}")
    for c in sorted({r["cond"] for r in R if r["same"]}):
        v = [r for r in R if r["cond"] == c and r["same"]]
        print(f"  same-convention control {c:24s} correct={fmt(v, lambda r: r['correct'])} over-converted/wrong={sum(r['acted'] and not r['correct'] for r in v)/len(v):.2f} asked={sum(r['asked'] for r in v)/len(v):.2f} n={len(v)}")


runs = {f[len("results_frontier_"):-6]: [json.loads(l) for l in open(f)] for f in glob.glob("results_frontier_*.jsonl")}
try: runs["sonnet"] = json.load(open("results_claude_sonnet.json"))
except FileNotFoundError: pass
MAIN = ["direct", "none", "card+resolver", "explicit+card+resolver"]
for m, R in sorted(runs.items()):
    err = sum(bool(r.get("error")) for r in R); R = [r for r in R if not r.get("error")]
    table(R, MAIN, f"{m} (errors={err})")
    amb = lambda r: r["concept"] in AMB
    for c1, c2 in [("direct", "none"), ("none", "card+resolver"), ("none", "explicit+card+resolver")]: print("   ", mcnemar(R, c1, c2, amb))
    v = [r for r in R if r["cond"] == "none" and not r["same"] and amb(r)]
    if v:
        cnt = collections.Counter(sender_unit(r) for r in v)
        print("    plain relay, sender's first message:", {k: f"{n/len(v):.2f} (correct {sum(r['correct'] for r in v if sender_unit(r)==k)/n:.2f})" for k, n in cnt.most_common()})
try:
    A = [r for r in map(json.loads, open("results_ablation.jsonl")) if "session limit" not in (r.get("error") or "")]
    errA = sum(bool(r.get("error")) for r in A); A = [r for r in A if not r.get("error")]
    for pair in sorted({(r["sender"], r["receiver"]) for r in A}):
        R = [r for r in A if (r["sender"], r["receiver"]) == pair]
        conds = sorted({r["cond"] for r in R if not r["same"]})
        table(R, conds, f"ABLATION sender={pair[0]} receiver={pair[1]} (errors in file={errA})")
        inf = [r for r in R if r.get("inferred_locale")]
        if inf: print(f"    sender-inferred locale correct: {sum(r['inferred_ok'] for r in inf)/len(inf):.2f} (n={len(inf)})")
except FileNotFoundError: pass

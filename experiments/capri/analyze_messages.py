"""Sender-message analyses on the clean Oct 3-5 runs (EXPERIMENT_PLAN.md A). Writes analysis_messages.txt and a blind
hand-labelling sheet (annotation/sheet.csv; the coder's labels go to annotation/key.csv).
Coder v2 (fixes v1 in analyze_frontier.py, which called "5 miles (about 8 km)" hedged): finds the principal's number in the
sender's first message and takes the unit attached to it as the primary unit; other units are a gloss. Categories:
  own, own+gloss       the principal's unit is primary (a conversion may be added)
  wrong, wrong+gloss   another unit is primary ("5 miles (about 8 km)" for a km principal is wrong+gloss)
  doubt                says it does not know the unit, or offers alternatives ("100 mph or km/h?")
  bare                 no unit at all
Rows from the old `sonnet` alias are reported but flagged: the model version behind them is unknown."""
import json, re, glob, random, collections, csv, os
import sys; sys.argv = sys.argv[:1]
from run import conv_unit, spec

PAT = {"C": r"°\s?C\b|celsius", "F": r"°\s?F\b|fahrenheit", "kmh": r"km/h|kph|kmh|km per hour|kilomet(re|er)s? per hour",
       "mph": r"\bmph\b|miles per hour|mi/h", "km": r"\bkms?\b|kilomet", "mi": r"\bmi\b|\bmiles?\b",
       "sqm": r"m²|\bm2\b|sq\.?\s?m\b|square met|sqm", "sqft": r"sq\.?\s?ft|square f(ee|oo)t|ft²|sqft",
       "CNY": r"yuan|RMB|CNY|元", "EUR": r"€|\beuros?\b|\bEUR\b", "GBP": r"£|\bpounds?\b|GBP", "KRW": r"₩|\bwon\b|KRW",
       "JPY": r"\byen\b|JPY|円", "INR": r"₹|rupees?|INR|\bRs\.?", "BRL": r"R\$|\brea(l|is)\b|BRL", "ILS": r"₪|shekels?|NIS|\bILS\b",
       "USD": r"(?<![A-Z])\$|dollars?|\bUSD\b"}
UNITS = {"temperature": ["C", "F"], "speed": ["kmh", "mph"], "distance": ["km", "mi"], "size": ["sqm", "sqft"],
         "price": ["CNY", "EUR", "GBP", "KRW", "JPY", "INR", "BRL", "ILS", "USD"]}
# strong: always doubt; weak: doubt only when no single unit is stated (they also appear in ordinary questions to the receiver)
DOUBT = re.compile(r"not sure|unsure|don'?t know|do not know|didn'?t specify|did not specify|not specified|unspecified|whichever unit|"
                   r"(unit|currency) (is|was) not (given|stated|mentioned)", re.I)
WEAK_DOUBT = re.compile(r"which (unit|currency)|what (unit|currency)|confirm (the|which) (unit|currency)", re.I)


def number_re(v):
    s = f"{v:.0f}" if float(v).is_integer() else f"{v:g}"
    if len(s) > 3:  # allow 300,000 / 300.000 / 300 000 / 300000
        groups = []; t = s
        while t: groups.insert(0, t[-3:]); t = t[:-3]
        return re.compile(r"(?<![\d.,])" + r"[,.  ]?".join(groups) + r"(?![\d])")
    return re.compile(r"(?<![\d.,])" + re.escape(s) + r"(?![\d])")


def unit_spans(text, concept, own):
    out = []
    for u in UNITS[concept]:
        for m in re.finditer(PAT[u], text, 0 if u.isupper() else re.I): out.append((m.start(), m.end(), u))
    if concept == "price":
        for m in re.finditer("¥", text): out.append((m.start(), m.end(), "CNY" if own == "CNY" else "JPY"))
    return sorted(out)


def code(text, concept, own, v):
    text = text or ""; spans = unit_spans(text, concept, own); units = {u for _, _, u in spans}
    if DOUBT.search(text): return "doubt"
    if not units: return "doubt" if WEAK_DOUBT.search(text) else "bare"
    for i in range(len(spans) - 1):  # "100 mph or km/h"
        a, b = spans[i], spans[i + 1]
        if a[2] != b[2] and re.fullmatch(r"\s*(,|/|or|\(or)\s*", text[a[1]:b[0]], re.I): return "doubt"
    if WEAK_DOUBT.search(text) and len(units) > 1: return "doubt"
    primary = None; m = number_re(v).search(text)
    if m:
        before = [s for s in spans if 0 <= m.start() - s[1] <= 3]       # "$300", "₩300,000"
        after = [s for s in spans if 0 <= s[0] - m.end() <= 25]          # "300 euros", "100 km/h"
        if before: primary = before[-1][2]
        elif after: primary = after[0][2]
    if primary is None: primary = spans[0][2]
    gloss = len(units - {primary}) > 0
    return ("own" if primary == own else "wrong") + ("+gloss" if gloss else "")


def load():
    rows = []
    for f in glob.glob("results_frontier_*.jsonl"):
        mdl = f[len("results_frontier_"):-6]
        if mdl == "claude-sonnet-5": continue  # written under the new harness (overnight), not Oct 3-5
        rows += [dict(json.loads(l), src="main", model=mdl) for l in open(f)]
    rows += [dict(r, src="main", model="sonnet") for r in json.load(open("results_claude_sonnet.json"))]
    for l in open("results_ablation.jsonl"):
        r = json.loads(l)
        if r.get("sender") == r.get("receiver"): rows.append(dict(r, src="ablation", model=r["sender"]))
    return [r for r in rows if not r.get("error") and r.get("sender_first") and r["cond"] != "direct" and not r["cond"].startswith("inject")]


def groups(rows, key):
    g = collections.defaultdict(list)
    for r in rows: g[key(r)].append(r)
    return sorted(g.items())


def pct(n, d): return f"{n/d:.2f}" if d else "  - "


if __name__ == "__main__":
    R = load(); out = []
    P = lambda *a: out.append(" ".join(str(x) for x in a))
    for r in R:
        own = r["culture"] and (spec({"concept": r["concept"], "culture": r["culture"]}, r["same"])[1] if r["same"] else conv_unit(r["concept"], r["culture"]))
        v = spec({"concept": r["concept"], "culture": r["culture"]}, r["same"])[0]
        r["own"], r["v"] = own, v; r["code2"] = code(r["sender_first"], r["concept"], own, v)
        r["copied"] = bool(number_re(v).search(r["sender_first"]))
    amb = [r for r in R if r["concept"] in ("speed", "distance", "price") and not r["same"]]
    P("# Sender-message analyses on the clean Oct 3-5 runs (coder v2). Ambiguous concepts, cross-convention items.")
    P("# 'sonnet' rows come from the old alias (model version unknown; see QUARANTINE.md) and are shown for reference only.\n")
    cats = ["own", "own+gloss", "wrong", "wrong+gloss", "doubt", "bare"]
    P("## 1. What the sender's first message says about the unit (share of messages), and how often the receiver ended correct / silently wrong")
    for (src, m), grp in groups(amb, lambda r: (r["src"], r["model"])):
        for c in sorted({r["cond"] for r in grp}):
            v = [r for r in grp if r["cond"] == c]
            if len(v) < 20: continue
            cnt = collections.Counter(r["code2"] for r in v)
            P(f"{src:8s} {m:18s} {c:34s} n={len(v):3d} | " + "  ".join(f"{k} {pct(cnt[k], len(v))}" for k in cats))
            P(" " * 66 + "| correct given: " + "  ".join(f"{k} {pct(sum(r['correct'] for r in v if r['code2'] == k), cnt[k])}" for k in cats if cnt[k]))
            P(" " * 66 + "| silent-wrong given: " + "  ".join(f"{k} {pct(sum(r['silent_wrong'] for r in v if r['code2'] == k), cnt[k])}" for k in cats if cnt[k]))
    P("\n## 2. Number copied vs value read correctly (answers 'Faithful, Not Corrective': the number survives, the convention does not)")
    for (m, c), grp in groups([r for r in amb if r["cond"] in ("none", "explicit", "explicit+card+resolver", "card+resolver")], lambda r: (r["model"], r["cond"])):
        if len(grp) < 20: continue
        P(f"{m:18s} {c:26s} n={len(grp):3d}  principal's number copied verbatim {pct(sum(r['copied'] for r in grp), len(grp))}   "
          f"receiver correct {pct(sum(r['correct'] for r in grp), len(grp))}   correct when copied {pct(sum(r['correct'] for r in grp if r['copied']), sum(r['copied'] for r in grp))}")
    P("\n## 3. Doubt suppression: share of first messages that admit not knowing the unit (doubt), plain vs explicit sender prompt")
    for m in sorted({r["model"] for r in amb}):
        line = []
        for c in ["none", "card", "resolver", "card+resolver", "inferred+resolver", "generic", "explicit", "explicit+inferred+resolver", "explicit+card+resolver", "typed"]:
            v = [r for r in amb if r["model"] == m and r["cond"] == c]
            if len(v) >= 20: line.append(f"{c} {pct(sum(r['code2'] == 'doubt' for r in v), len(v))} (n={len(v)})")
        if line: P(f"{m:18s} " + "; ".join(line))
    P("\n## 4. Plausibility on the sender side (price): budgets implausible as US dollars (KRW 300,000 / JPY 30,000 / INR 15,000) vs plausible ones")
    IMPL = {"KRW", "JPY", "INR"}
    for m in sorted({r["model"] for r in amb}):
        for c in ["none", "explicit", "explicit+inferred+resolver"]:
            v = [r for r in amb if r["model"] == m and r["cond"] == c and r["concept"] == "price"]
            if len(v) < 15: continue
            for lab, f in [("implausible", lambda r: r["own"] in IMPL), ("plausible", lambda r: r["own"] not in IMPL)]:
                w = [r for r in v if f(r)]; cnt = collections.Counter(r["code2"] for r in w)
                bare = [r for r in w if r["code2"] == "bare"]
                P(f"{m:18s} {c:28s} {lab:11s} n={len(w):3d} | " + "  ".join(f"{k} {pct(cnt[k], len(w))}" for k in cats)
                  + f" | silent-wrong overall {pct(sum(r['silent_wrong'] for r in w), len(w))}, given bare {pct(sum(r['silent_wrong'] for r in bare), len(bare))} (n={len(bare)})")
    open("analysis_messages.txt", "w").write("\n".join(out) + "\n")
    print("\n".join(out[:12])); print(f"... ({len(out)} lines) -> analysis_messages.txt")
    # blind hand-labelling sheet: 150 messages stratified by coder label x model (old sonnet alias excluded)
    pool = [r for r in amb if r["model"] != "sonnet"]
    rng = random.Random(0); by = collections.defaultdict(list)
    for r in pool: by[r["code2"]].append(r)
    picked = []
    for k in cats: rng.shuffle(by[k]); picked += by[k][:25]
    rest = [r for r in pool if r not in picked]; rng.shuffle(rest); picked += rest[:150 - len(picked)]
    rng.shuffle(picked); os.makedirs("annotation", exist_ok=True)
    COUNTRY = lambda c: c.replace("_", " ")
    with open("annotation/sheet.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["id", "concept", "principal_country", "principal_means", "sender_message",
                                         "primary_unit (own/other/none)", "another_unit_also_given (y/n)", "admits_not_knowing_or_offers_options (y/n)", "notes"])
        for i, r in enumerate(picked): w.writerow([i, r["concept"], COUNTRY(r["culture"]), f"{r['v']:g} {r['own']}", r["sender_first"], "", "", "", ""])
    with open("annotation/key.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["id", "model", "cond", "coder_v2", "file"])
        for i, r in enumerate(picked): w.writerow([i, r["model"], r["cond"], r["code2"], r["file"]])
    print(f"annotation/sheet.csv: {len(picked)} messages (blind); labels in annotation/key.csv")

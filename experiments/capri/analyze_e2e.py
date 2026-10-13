"""Analysis for the end-to-end runs (results_e2e.jsonl; EXPERIMENT_PLAN.md E). Per sender=receiver model, split and condition:
six mutually exclusive outcomes (correct without asking, asked then correct, silently wrong, asked then wrong, no action;
plus needless asking on same-unit controls), agent turns, escalations to the principal, 95% CIs bootstrapped over
culture x concept clusters, paired exact McNemar tests of the method against every baseline, and cost-weighted utility
  U = correct - la * agent_questions - lp * escalations - lw * silently_wrong
swept over question costs, with the regret against an oracle that asks only when the unit actually mismatches.
Usage: python analyze_e2e.py [--split heldout|dev] [--model M]"""
import json, random, collections, math, argparse

METHOD = "ground+xcheck+readback"
OUTCOMES = ["correct", "asked_correct", "silent_wrong", "asked_wrong", "no_action"]


def cci(rows, f, B=2000):
    if not rows: return (float("nan"),) * 3
    cl = collections.defaultdict(list)
    for r in rows: cl[(r["culture"], r["concept"])].append(float(f(r)))
    keys = list(cl); rng = random.Random(0); m = sum(sum(v) for v in cl.values()) / len(rows); bs = []
    for _ in range(B):
        s = [cl[rng.choice(keys)] for _ in keys]; n = sum(len(x) for x in s); bs.append(sum(sum(x) for x in s) / n)
    bs.sort(); return m, bs[int(.025 * B)], bs[int(.975 * B)]


def fmt(rows, f): m, lo, hi = cci(rows, f); return f"{m:.2f} [{lo:.2f},{hi:.2f}]"


def mcnemar(a, b, key):
    k = [f for f in a if f in b]; n01 = sum(not key(a[f]) and key(b[f]) for f in k); n10 = sum(key(a[f]) and not key(b[f]) for f in k)
    n = n01 + n10
    if n == 0: return f"+0/-0 of {len(k)}"
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(min(n01, n10) + 1)) / 2 ** n)
    return f"+{n01}/-{n10} of {len(k)}, p={p:.3g}"


def utility(r, la, lp, lw):
    return float(r["correct"]) - la * r["asks"] - lp * r["escalations"] - lw * float(r["silent_wrong"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--split", default="heldout"); ap.add_argument("--model", default=None)
    ap.add_argument("--file", default="results_e2e.jsonl")
    a = ap.parse_args()
    R = [json.loads(l) for l in open(a.file)]
    err = sum(bool(r.get("error")) for r in R); R = [r for r in R if not r.get("error") and r["split"] == a.split]
    print(f"{len(R)} ok rows in split={a.split} ({err} errored rows in file)")
    models = sorted({r["sender"] for r in R if r["sender"] == r["receiver"]})
    for m in models if not a.model else [a.model]:
        M = [r for r in R if r["sender"] == m and r["receiver"] == m and r.get("rep", 0) == 0]
        X = [r for r in M if not r["same"]]; Sm = [r for r in M if r["same"]]
        conds = sorted({r["cond"] for r in X}, key=lambda c: (c != METHOD, c))
        print(f"\n== {m}  (cross-convention n={len(X)}, same-unit controls n={len(Sm)})")
        print(f"  {'condition':36s} {'correct (any route)':22s} {'silent wrong':22s} " + " ".join(f"{o[:9]:>9s}" for o in OUTCOMES) + "  asks  esc  n")
        for c in conds:
            v = [r for r in X if r["cond"] == c]
            oc = collections.Counter(r["outcome"] for r in v)
            print(f"  {c:36s} {fmt(v, lambda r: r['correct']):22s} {fmt(v, lambda r: r['silent_wrong']):22s} "
                  + " ".join(f"{oc[o]/len(v):9.2f}" for o in OUTCOMES)
                  + f" {sum(r['asks'] for r in v)/len(v):5.2f} {sum(r['escalations'] for r in v)/len(v):4.2f} {len(v):3d}")
        for c in sorted({r["cond"] for r in Sm}):
            v = [r for r in Sm if r["cond"] == c]
            print(f"  same-unit control {c:30s} correct={sum(r['correct'] for r in v)/len(v):.2f} over-converted={sum(r['acted'] and not r['correct'] for r in v)/len(v):.2f} "
                  f"needless asks={sum(r['asked'] for r in v)/len(v):.2f} escalations={sum(r['escalations'] for r in v)/len(v):.2f} n={len(v)}")
        by = {c: {r["file"]: r for r in X if r["cond"] == c} for c in conds}
        if METHOD in by:
            print(f"  paired vs {METHOD} (+ = method better):")
            for c in conds:
                if c == METHOD: continue
                print(f"    {c:34s} correct {mcnemar(by[c], by[METHOD], lambda r: r['correct'])};  "
                      f"silent-wrong {mcnemar(by[METHOD], by[c], lambda r: r['silent_wrong'])}")
        print("  cost-weighted utility (lw = cost of a silent error; la = agent question; lp = escalation to the principal):")
        grid = [(0.05, 0.25, 1), (0.05, 0.25, 3), (0.1, 0.5, 3), (0.1, 0.5, 10), (0.25, 1.0, 10)]
        print("    " + " ".join(f"la={la},lp={lp},lw={lw}".rjust(20) for la, lp, lw in grid))
        for c in conds:
            v = [r for r in X if r["cond"] == c]
            print(f"    {c:34s}" + " ".join(f"{sum(utility(r, *g) for r in v)/len(v):20.3f}" for g in grid))
        # oracle: ask exactly once (one agent question) whenever the unit mismatches -> always correct; on cross-convention items
        # every item mismatches, so the oracle utility is 1 - la; regret = oracle - condition
        print("    regret vs oracle that asks once only on mismatch:")
        for c in conds:
            v = [r for r in X if r["cond"] == c]
            print(f"    {c:34s}" + " ".join(f"{(1 - la) - sum(utility(r, la, lp, lw) for r in v)/len(v):20.3f}" for la, lp, lw in grid))

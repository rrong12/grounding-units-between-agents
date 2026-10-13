"""Every number in the paper comes from here (mock reviews 1-3 all flagged text/table mismatches). Reads the result files in
../capri and writes tables/*.tex plus numbers.tex, whose \\N{key} macros the text uses for in-line numbers (an unknown key
prints red ??key in the PDF). Percentages are rounded to whole points; CIs are 95% bootstraps over culture x concept
clusters and p-values exact McNemar tests on paired items, both as in capri/analyze_e2e.py.
Data: claims 1-3 = clean Oct 3-5 runs (results_frontier_*, results_claude_sonnet.json, results_ablation.jsonl);
E1 dev = results_e2e_dev.jsonl (first CLI account); E2 held-out = results_e2e_heldout.jsonl (second CLI account).
Usage: python3 make_tables.py"""
import json, os, sys, glob, collections, tempfile
os.environ.setdefault("OPENROUTER_API_KEY", "unused")  # llm.py wants a key at import; nothing here calls a model
os.environ.setdefault("CODEX_CLI_WORK", tempfile.mkdtemp())  # codex_mcp.py links ~/.codex/auth.json at import
HERE = os.path.dirname(os.path.abspath(__file__)); CAPRI = os.path.join(HERE, "..", "capri")
sys.path.insert(0, CAPRI); os.chdir(CAPRI); sys.argv = sys.argv[:1]
from analyze_e2e import cci, utility
import analyze_messages as am
from math import comb, floor, log10

AMB = {"speed", "distance", "price"}
METHOD = "ground+xcheck+readback"
E2_MODELS = [("claude-opus-5-5", "Opus 5.5"), ("claude-sonnet-5", "Sonnet 5"), ("claude-haiku-4-5-20251001", "Haiku 4.5")]
SHORT = {"claude-opus-5-5": "opus", "claude-sonnet-5": "sonnet", "claude-haiku-4-5-20251001": "haiku"}
E2_CONDS = [(METHOD, "\\textbf{Ours}: ground + cross-check + read-back", "method"),
            ("explicit+inferred+resolver+hybrid", "Hybrid confidence channel", "hybrid"),
            ("explicit+inferred+resolver", "Explicit + inferred locale + resolver", "resolver"),
            ("explicit", "Explicit units \\citep{miao2026capri}", "explicit"),
            ("typed", "Typed JSON, mandatory unit field", "typed"),
            ("pcot", "Pragmatic CoT sender \\citep{miao2026capri}", "pcot"),
            ("selfunc", "Receiver asks if uncertain \\citep{matsnev2026uncertainty}", "selfunc"),
            ("none", "Plain relay", "none")]
# claims 1-3: model key in the Oct 3-5 files -> (label, macro key); the old `sonnet` alias has an unknown model version
OLD = [("opus", "Opus 5.5", "opus"), ("sonnet", "Sonnet$^\\dagger$", "sonnet"), ("haiku", "Haiku 4.5", "haiku"),
       ("claude-fable-5-1", "Fable 5.1", "fable"), ("gpt-6.1-sol", "GPT-6.1", "gpt"), ("ling-3.1-flash", "Ling-3.1-Flash", "ling")]
NUM = {}


def pc(x): return f"{100 * x:.0f}"
def put(key, val): NUM[key] = val; return val
def mean(v, f): return sum(float(f(r)) for r in v) / len(v) if v else float("nan")


def p_exact(a, b, key):
    """paired exact McNemar: n01 = items where b has key and a not; returns (n01, n10, p)"""
    k = [f for f in a if f in b]; n01 = sum(not key(a[f]) and key(b[f]) for f in k); n10 = sum(key(a[f]) and not key(b[f]) for f in k)
    n = n01 + n10
    return n01, n10, (1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(n01, n10) + 1)) / 2 ** n))


def fmt_p(p): return "{<}10^{-3}" if p < 1e-3 else f"{{=}}{p:.2f}" if p >= 0.01 else f"{{=}}{p:.3f}"  # use as $p\N{key}$


def jl(f): return [json.loads(l) for l in open(f)]


def write(name, s): open(os.path.join(HERE, "tables", name), "w").write(s)


# ---------------------------------------------------------------- claims 1-3 (clean Oct 3-5 runs)
FR = {f[len("results_frontier_"):-6]: [r for r in jl(f) if not r.get("error")] for f in glob.glob("results_frontier_*.jsonl")}
FR["sonnet"] = [r for r in json.load(open("results_claude_sonnet.json")) if not r.get("error")]
ABL = [r for r in jl("results_ablation.jsonl") if not r.get("error") and r["sender"] == r["receiver"]]
MSG = am.load()
for r in MSG:
    own = am.spec({"concept": r["concept"], "culture": r["culture"]}, r["same"])[1] if r["same"] else am.conv_unit(r["concept"], r["culture"])
    v = am.spec({"concept": r["concept"], "culture": r["culture"]}, r["same"])[0]
    r["own"], r["v"], r["code2"], r["copied"] = own, v, am.code(r["sender_first"], r["concept"], own, v), bool(am.number_re(v).search(r["sender_first"]))
MSG = [r for r in MSG if r["concept"] in AMB and not r["same"]]


def cells(R, cond): return [r for r in R if r["cond"] == cond and not r["same"] and r["concept"] in AMB]


# Table 1: single agent vs plain relay
rows = []
for m, lab, k in OLD:
    d, n = cells(FR[m], "direct"), cells(FR[m], "none")
    cp = [r for r in MSG if r["model"] == m and r["src"] == "main" and r["cond"] == "none"]
    vals = [put(f"c1:{k}:direct:correct", pc(mean(d, lambda r: r["correct"]))), put(f"c1:{k}:direct:silent", pc(mean(d, lambda r: r["silent_wrong"]))),
            put(f"c1:{k}:relay:correct", pc(mean(n, lambda r: r["correct"]))), put(f"c1:{k}:relay:silent", pc(mean(n, lambda r: r["silent_wrong"]))),
            put(f"c1:{k}:relay:copied", pc(mean(cp, lambda r: r["copied"])))]
    put(f"c1:{k}:n", str(len(n)))
    rows.append(f"{lab} & {vals[0]} & {vals[1]} & {vals[2]} & {vals[3]} & {vals[4]} & {len(n)} \\\\")
write("t1_failure.tex", "\\begin{tabular}{lrrrrrr}\n\\toprule\n & \\multicolumn{2}{c}{Single agent} & \\multicolumn{3}{c}{Plain relay} & \\\\\n"
      "\\cmidrule(lr){2-3}\\cmidrule(lr){4-6}\nModel & Corr. & Silent & Corr. & Silent & Copied & $n$ \\\\\n\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")
put("c1:direct:max", str(max(int(NUM[f"c1:{k}:direct:correct"]) for _, _, k in OLD)))
put("c1:relay:min", str(min(int(NUM[f"c1:{k}:relay:correct"]) for _, _, k in OLD))); put("c1:relay:max", str(max(int(NUM[f"c1:{k}:relay:correct"]) for _, _, k in OLD)))
put("c1:copied:min", str(min(int(NUM[f"c1:{k}:relay:copied"]) for _, _, k in OLD)))
put("c1:direct:silent:min", str(min(int(NUM[f"c1:{k}:direct:silent"]) for _, _, k in OLD))); put("c1:direct:silent:max", str(max(int(NUM[f"c1:{k}:direct:silent"]) for _, _, k in OLD)))
# what the relay sender's first message says about the unit (coder v2), pooled over the six models, and how often it ends correct
MCAT = {"own": ("own", "own+gloss"), "wrong": ("wrong", "wrong+gloss"), "doubt": ("doubt",), "bare": ("bare",)}
pool = [r for r in MSG if r["src"] == "main" and r["cond"] == "none" and r["model"] in {m for m, _, _ in OLD}]
for cat, codes in MCAT.items():
    w = [r for r in pool if r["code2"] in codes]
    put(f"c1:msg:{cat}:share", pc(len(w) / len(pool))); put(f"c1:msg:{cat}:correct", pc(mean(w, lambda r: r["correct"])))
    put(f"c1:msg:{cat}:silent", pc(mean(w, lambda r: r["silent_wrong"])))
put("c1:msg:n", f"{len(pool):,}".replace(",", "{,}"))
# silent errors in Table 1 that write the principal's raw number into the tool's unit
sw = [r for m, _, _ in OLD for c in ("direct", "none") for r in cells(FR[m], c) if r["silent_wrong"]]
raw = sum(bool(r["args"]) and abs(float(next(iter(r["args"].values()))) - am.spec(r)[0]) < 1e-6 for r in sw)
put("c1:silent:n", str(len(sw))); put("c1:silent:raw", pc(raw / len(sw)))

# Table 2: counterfactual sender messages injected into the receiver
INJ = [("inject:own", "Principal's unit"), ("inject:hedged", "Hedged (two units)"), ("inject:bare", "Bare number"), ("inject:wrong", "Wrong unit")]
REC = [("opus", "Opus", "opus"), ("sonnet", "Sonnet$^\\dagger$", "sonnet"), ("haiku", "Haiku", "haiku"), ("claude-fable-5-1", "Fable", "fable")]
rows = []
for cond, lab in INJ:
    line = [lab]
    for m, _, k in REC:
        v = cells([r for r in ABL if r["sender"] == m], cond); kk = cond.split(":")[1]
        line.append(f"{put(f'c2:{k}:{kk}:correct', pc(mean(v, lambda r: r['correct'])))} / {put(f'c2:{k}:{kk}:silent', pc(mean(v, lambda r: r['silent_wrong'])))}")
    rows.append(" & ".join(line) + " \\\\")
nI = len(cells([r for r in ABL if r["sender"] == "opus"], "inject:own")); put("c2:n", str(nI))
write("t2_injection.tex", "\\begin{tabular}{l" + "c" * len(REC) + "}\n\\toprule\nInjected sender message & " + " & ".join(l for _, l, _ in REC)
      + " \\\\\n\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")
for kk in ("own", "hedged", "bare", "wrong"):
    for s in ("correct", "silent"):
        xs = [int(NUM[f"c2:{k}:{kk}:{s}"]) for _, _, k in REC]; put(f"c2:{kk}:{s}:min", str(min(xs))); put(f"c2:{kk}:{s}:max", str(max(xs)))

# Table 3: explicit units next to receiver safeguards (card + resolver): accuracy up, doubt gone, silent errors up
rows = []
for m, lab, k in [o for o in OLD if o[0] != "gpt-6.1-sol"]:
    a, b = cells(FR[m], "card+resolver"), cells(FR[m], "explicit+card+resolver")
    dn = [r for r in MSG if r["model"] == m and r["cond"] == "none"]; de = [r for r in MSG if r["model"] == m and r["cond"] == "explicit+card+resolver"]
    wr = [r for r in de if r["code2"].startswith("wrong")]
    vals = [put(f"c3:{k}:doubt:plain", pc(mean(dn, lambda r: r["code2"] == "doubt"))), put(f"c3:{k}:doubt:explicit", pc(mean(de, lambda r: r["code2"] == "doubt"))),
            put(f"c3:{k}:wrongunit", pc(mean(de, lambda r: r["code2"].startswith("wrong")))),
            put(f"c3:{k}:correct:base", pc(mean(a, lambda r: r["correct"]))), put(f"c3:{k}:correct:explicit", pc(mean(b, lambda r: r["correct"]))),
            put(f"c3:{k}:silent:base", pc(mean(a, lambda r: r["silent_wrong"]))), put(f"c3:{k}:silent:explicit", pc(mean(b, lambda r: r["silent_wrong"])))]
    put(f"c3:{k}:wrongunit:silent", pc(mean(wr, lambda r: r["silent_wrong"])) if wr else "--"); put(f"c3:{k}:wrongunit:n", str(len(wr)))
    rows.append(f"{lab} & {vals[0]} $\\to$ {vals[1]} & {vals[2]} & {vals[3]} $\\to$ {vals[4]} & {vals[5]} $\\to$ {vals[6]} \\\\")
write("t3_explicit.tex", "\\begin{tabular}{lcccc}\n\\toprule\n & Sender doubts & Asserts & Correct & Silently wrong \\\\\n"
      "Model & plain $\\to$ explicit & wrong unit & \\multicolumn{2}{c}{card+resolver $\\to$ + explicit} \\\\\n\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")
# plausibility on the sender side (Opus, explicit, price): wrong-currency assertions on budgets implausible vs plausible as USD
IMPL = {"KRW", "JPY", "INR"}
v = [r for r in MSG if r["model"] == "opus" and r["cond"] == "explicit" and r["concept"] == "price"]
for lab, f in [("implausible", lambda r: r["own"] in IMPL), ("plausible", lambda r: r["own"] not in IMPL)]:
    w = [r for r in v if f(r)]; put(f"c3:plaus:{lab}:wrong", str(sum(r["code2"].startswith("wrong") for r in w))); put(f"c3:plaus:{lab}:n", str(len(w)))

# Haiku and Fable rows behind Tables 1 and 3 were run after the CLI began injecting the account email (Limitations): rows that
# mention it, and the largest change in any Table 1/3 cell when they are dropped. The regex also matches the release's scrubbed form.
import re
EMR = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\[email removed\]|\[institution removed\]|\buniversity email\b|email is from\b", re.I)
mentions = lambda r: bool(EMR.search(json.dumps(r, ensure_ascii=False)))
for m, k in [("haiku", "haiku"), ("claude-fable-5-1", "fable")]:
    put(f"inj:{k}:mention", str(sum(mentions(r) for r in FR[m]))); put(f"inj:{k}:rows", str(len(FR[m])))
    diffs = []
    for c in ("direct", "none", "card+resolver", "explicit+card+resolver"):
        a = cells(FR[m], c); b = [r for r in a if not mentions(r)]
        for f in (lambda r: r["correct"], lambda r: r["silent_wrong"]): diffs.append(abs(100 * mean(a, f) - 100 * mean(b, f)))
    put(f"inj:{k}:maxshift", f"{max(diffs):.0f}")
put("inj:maxshift", str(max(int(NUM["inj:haiku:maxshift"]), int(NUM["inj:fable:maxshift"]))))

# ---------------------------------------------------------------- E2 held-out (main result) and E1 dev ablations
E2 = [r for r in jl("results_e2e_heldout.jsonl") if not r.get("error") and r["split"] == "heldout" and r["sender"] == r["receiver"] and r.get("rep", 0) == 0]
E1 = [r for r in jl("results_e2e_dev.jsonl") if not r.get("error") and r["split"] == "dev" and r["sender"] == r["receiver"] and r.get("rep", 0) == 0]
X2 = lambda m, c: [r for r in E2 if r["sender"] == m and r["cond"] == c and not r["same"]]
put("e2:n", str(len(X2("claude-opus-5-5", METHOD)))); put("e2:episodes", f"{len(E2):,}".replace(",", "{,}"))

# Table 4: main result, correct / silent wrong per model, plus the worst model; best real condition per column in bold
cols = {}
for m, _ in E2_MODELS:
    for c, _, ck in E2_CONDS:
        v = X2(m, c); cols[(m, c)] = (mean(v, lambda r: r["correct"]), mean(v, lambda r: r["silent_wrong"]))
        k = f"e2:{SHORT[m]}:{ck}"; put(k + ":correct", pc(cols[(m, c)][0])); put(k + ":silent", pc(cols[(m, c)][1]))
        mu, lo, hi = cci(v, lambda r: r["correct"]); put(k + ":correct:lo", pc(lo)); put(k + ":correct:hi", pc(hi))
        oc = collections.Counter(r["outcome"] for r in v)
        for o in ("correct", "asked_correct", "silent_wrong", "asked_wrong", "no_action"): put(f"{k}:{o.replace('_', '')}:share", pc(oc[o] / len(v)))
        put(k + ":asks", f"{mean(v, lambda r: r['asks']):.2f}"); put(k + ":esc", f"{mean(v, lambda r: r['escalations']):.2f}")
    v = X2(m, "stated"); put(f"e2:{SHORT[m]}:stated:correct", pc(mean(v, lambda r: r["correct"]))); put(f"e2:{SHORT[m]}:stated:silent", pc(mean(v, lambda r: r["silent_wrong"])))
worst = {c: (min(cols[(m, c)][0] for m, _ in E2_MODELS), max(cols[(m, c)][1] for m, _ in E2_MODELS)) for c, _, _ in E2_CONDS}
for c, _, ck in E2_CONDS: put(f"e2:worst:{ck}:correct", pc(worst[c][0])); put(f"e2:worst:{ck}:silent", pc(worst[c][1]))
best = {m: max(pc(cols[(m, c)][0]) for c, _, _ in E2_CONDS) for m, _ in E2_MODELS}
bestw = max(pc(worst[c][0]) for c, _, _ in E2_CONDS)
B = lambda s, cond: f"\\textbf{{{s}}}" if cond else s
rows = []
for c, lab, ck in E2_CONDS:
    cell = [B(pc(cols[(m, c)][0]), pc(cols[(m, c)][0]) == best[m]) + " / " + pc(cols[(m, c)][1]) for m, _ in E2_MODELS]
    rows.append(f"{lab} & " + " & ".join(cell) + f" & {B(pc(worst[c][0]), pc(worst[c][0]) == bestw)} / {pc(worst[c][1])} \\\\" + ("\n\\midrule" if c == METHOD else ""))
rows.append("\\midrule\n\\textit{Control: principal states the unit} & " + " & ".join(f"\\textit{{{NUM[f'e2:{SHORT[m]}:stated:correct']} / {NUM[f'e2:{SHORT[m]}:stated:silent']}}}" for m, _ in E2_MODELS) + " & \\\\")
write("t4_main.tex", "\\begin{tabular}{lcccc}\n\\toprule\nCondition & " + " & ".join(l for _, l in E2_MODELS) + " & Worst model \\\\\n\\midrule\n"
      + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")

# paired tests, method vs each baseline (correct; silent wrong)
for m, _ in E2_MODELS:
    by = {c: {r["file"]: r for r in X2(m, c)} for c, _, _ in E2_CONDS}
    for c, _, ck in E2_CONDS[1:]:
        n01, n10, p = p_exact(by[c], by[METHOD], lambda r: r["correct"]); k = f"e2:{SHORT[m]}:{ck}"
        put(k + ":p", fmt_p(p)); put(k + ":wins", str(n01)); put(k + ":losses", str(n10))
        put(k + ":psilent", fmt_p(p_exact(by[METHOD], by[c], lambda r: r["silent_wrong"])[2]))
weak = [p_exact({r["file"]: r for r in X2(m, c)}, {r["file"]: r for r in X2(m, METHOD)}, lambda r: r["correct"])[2]
        for m, _ in E2_MODELS for c in ("none", "pcot", "selfunc")]
put("e2:weak:pmax", f"10^{{{floor(log10(max(weak))) + 1}}}")

# per-concept breakdown (correct / no action) and same-unit controls, for the appendix and the in-text "where the gain comes from"
CONCEPTS = ["distance", "price", "speed"]
rows = []
for m, lab in E2_MODELS:
    for i, (c, clab, ck) in enumerate(E2_CONDS + [("stated", "\\textit{Control: principal states the unit}", "stated")]):
        cl = []
        for con in CONCEPTS:
            v = [r for r in X2(m, c) if r["concept"] == con]
            a, b = pc(mean(v, lambda r: r["correct"])), pc(mean(v, lambda r: r["outcome"] == "no_action"))
            put(f"e2:{SHORT[m]}:{ck}:{con}:correct", a); put(f"e2:{SHORT[m]}:{ck}:{con}:noaction", b); cl.append(f"{a} / {b}")
        rows.append((f"\\multirow{{9}}{{*}}{{{lab}}}" if i == 0 else "") + f" & {clab} & " + " & ".join(cl) + " \\\\")
    rows.append("\\midrule")
write("tA_concept.tex", "\\begin{tabular}{llccc}\n\\toprule\nModel & Condition & " + " & ".join(c.capitalize() for c in CONCEPTS)
      + " \\\\\n\\midrule\n" + "\n".join(rows[:-1]) + "\n\\bottomrule\n\\end{tabular}\n")
for con in CONCEPTS: put(f"e2:n:{con}", str(len([r for r in X2('claude-opus-5-5', METHOD) if r['concept'] == con])))

rows = []
for m, lab in E2_MODELS:
    for c in sorted({r["cond"] for r in E2 if r["sender"] == m and r["same"]}, key=lambda c: (c != METHOD, c)):
        v = [r for r in E2 if r["sender"] == m and r["cond"] == c and r["same"]]; ck = dict((a, k) for a, _, k in E2_CONDS)[c]
        vals = [pc(mean(v, lambda r: r["correct"])), pc(mean(v, lambda r: r["acted"] and not r["correct"])), pc(mean(v, lambda r: r["asked"])), f"{mean(v, lambda r: r['escalations']):.2f}"]
        for name, x in zip(("correct", "overconv", "asked", "esc"), vals): put(f"e2same:{SHORT[m]}:{ck}:{name}", x)
        rows.append(f"{lab} & {dict((a, l) for a, l, _ in E2_CONDS)[c]} & " + " & ".join(vals) + f" & {len(v)} \\\\")
put("e2same:n", str(len([r for r in E2 if r["sender"] == "claude-opus-5-5" and r["cond"] == METHOD and r["same"]])))
write("tA_same.tex", "\\begin{tabular}{llrrrrr}\n\\toprule\nModel & Condition & Correct & Over-conv. & Asked & Esc. & $n$ \\\\\n\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")

# cost-weighted utility U = correct - la*asks - lp*escalations - lw*silent_wrong, swept over costs (appendix)
GRID = [(0.05, 0.25, 1), (0.05, 0.25, 3), (0.1, 0.5, 3), (0.1, 0.5, 10), (0.25, 1.0, 10)]
rows, wins = [], collections.Counter()
for m, lab in E2_MODELS:
    U = {c: [mean(X2(m, c), lambda r: utility(r, *g)) for g in GRID] for c, _, _ in E2_CONDS}
    for j in range(len(GRID)):
        if max(U, key=lambda c: U[c][j]) == METHOD: wins[m] += 1
    put(f"e2:{SHORT[m]}:utility:wins", str(wins[m]))
    for i, (c, clab, _) in enumerate(E2_CONDS):
        top = [U[c][j] == max(U[d][j] for d in U) for j in range(len(GRID))]
        rows.append((f"\\multirow{{8}}{{*}}{{{lab}}}" if i == 0 else "") + f" & {clab} & " + " & ".join(B(f"{u:.2f}", t) for u, t in zip(U[c], top)) + " \\\\")
    rows.append("\\midrule")
write("tA_utility.tex", "\\begin{tabular}{ll" + "r" * len(GRID) + "}\n\\toprule\n & $(\\lambda_a,\\lambda_p,\\lambda_w)$ & " + " & ".join(f"({a},{p},{w})" for a, p, w in GRID)
      + " \\\\\n\\midrule\n" + "\n".join(rows[:-1]) + "\n\\bottomrule\n\\end{tabular}\n")
put("utility:grid:n", str(len(GRID)))

# Table 5: step ablations on the development set (E1: a column per model whose cells are all complete)
ABL_C = [(METHOD, "Full method", "full"), ("ground", "Ground only", "ground"), ("ground+xcheck", "Ground + cross-check", "groundxcheck"),
         ("xcheck+readback", "Cross-check + read-back (no grounding)", "xcheckreadback"), ("none", "Plain relay", "none")]
E1_N = len([r for r in E1 if r["sender"] == "claude-opus-5-5" and r["cond"] == METHOD])
E1_MODELS = [(m, l) for m, l in E2_MODELS if all(len([r for r in E1 if r["sender"] == m and r["cond"] == c]) == E1_N for c, _, _ in ABL_C)]
put("e1:models", str(len(E1_MODELS)))
rows = []
for c, lab, ck in ABL_C:
    cl = []
    for m, _ in E1_MODELS:
        v = [r for r in E1 if r["sender"] == m and r["cond"] == c and not r["same"]]
        a, s, n = pc(mean(v, lambda r: r["correct"])), pc(mean(v, lambda r: r["silent_wrong"])), pc(mean(v, lambda r: r["outcome"] == "no_action"))
        put(f"e1:{SHORT[m]}:{ck}:correct", a); put(f"e1:{SHORT[m]}:{ck}:silent", s); put(f"e1:{SHORT[m]}:{ck}:noaction", n); cl.append(f"{a} / {s} / {n}")
    rows.append(f"{lab} & " + " & ".join(cl) + " \\\\")
put("e1:n", str(E1_N))
write("t5_ablation.tex", "\\begin{tabular}{l" + "c" * len(E1_MODELS) + "}\n\\toprule\nCondition & " + " & ".join(l for _, l in E1_MODELS) + " \\\\\n\\midrule\n"
      + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")

# six mutually exclusive outcomes with CIs (appendix)
rows = []
for m, lab in E2_MODELS:
    for i, (c, clab, _) in enumerate(E2_CONDS + [("stated", "\\textit{Control: principal states the unit}", "stated")]):
        v = X2(m, c); oc = collections.Counter(r["outcome"] for r in v)
        ci = lambda f: "{:.0f} [{:.0f},{:.0f}]".format(*(100 * x for x in cci(v, f)))
        rows.append((f"\\multirow{{9}}{{*}}{{{lab}}}" if i == 0 else "") + f" & {clab} & {ci(lambda r: r['correct'])} & {ci(lambda r: r['silent_wrong'])} & "
                    + " & ".join(pc(oc[o] / len(v)) for o in ("correct", "asked_correct", "asked_wrong", "no_action"))
                    + f" & {mean(v, lambda r: r['asks']):.2f} & {mean(v, lambda r: r['escalations']):.2f} \\\\")
    rows.append("\\midrule")
write("tA_outcomes.tex", "\\begin{tabular}{llcccccc rr}\n\\toprule\nModel & Condition & Correct & Silent wrong & Corr.\\ (no ask) & Asked$\\to$corr. & Asked$\\to$wrong & No action & Asks & Esc. \\\\\n\\midrule\n"
      + "\n".join(rows[:-1]) + "\n\\bottomrule\n\\end{tabular}\n")

# prompts, verbatim from the runners (appendix)
import run as RN, run_ablation as RA, run_e2e as RE
def tex(s): return "".join({"\\": "\\textbackslash{}", "{": "\\{", "}": "\\}", "_": "\\_", "$": "\\$", "%": "\\%", "&": "\\&", "#": "\\#", "^": "\\^{}", "~": "\\~{}", "\n": " "}.get(ch, ch) for ch in s.strip())
P = [("Sender (all conditions)", RN.SENDER + RE.LOGI_S), ("Sender: plain format", RE.PLAIN_FMT), ("Sender: principal access (all conditions)", RE.PRINCIPAL_S),
     ("Sender: explicit units", RN.EXPLICIT), ("Sender: Pragmatic CoT", RE.PCOT_S), ("Sender: typed JSON", RA.TYPED_S), ("Sender: hybrid confidence", RA.HYB_S),
     ("Sender: notes format (ground, Pragmatic CoT)", RE.REASONED), ("\\textbf{Method}, sender: ground", RE.GROUND_S), ("\\textbf{Method}, sender: read-back", RE.RB_S),
     ("Receiver (all conditions; speed, km/h principal)", RN.RECV[("speed", "mph")][0] + RE.LOGI_R + " Use set_speed_alert to act."),
     ("Receiver: resolver", RN.RESOLVE), ("Receiver: hybrid", RA.HYB_R), ("Receiver: asks if uncertain", RE.SELFUNC_R),
     ("\\textbf{Method}, receiver: cross-check", RE.XCHECK_R), ("\\textbf{Method}, receiver's first turn: read-back", RE.RB_TURN),
     ("Requests", " / ".join(RN.INSTR[c] for c in ("speed", "distance", "price"))),
     ("Principal's deferral to non-unit questions", RE.principal_answer("Which venue?", 5, "km"))]
write("prompts.tex", "\n".join(f"\\item[{lab}] \\texttt{{\\small {tex(s)}}}" for lab, s in P) + "\n")

# harness checks quoted in Limitations: injected-email mentions in E2; receiver turns written in the sender's voice (label bug)
EM = re.compile(r"[\w.]+@[\w.]+|\.edu\b|\[email removed\]", re.I); VOICE = re.compile(r"\b(my principal|on behalf of my|I'?m writing on behalf)\b", re.I)
put("e2:email:hits", str(sum(any(EM.search(t) for _, t in r["transcript"]) for r in E2)))
for m, _ in E2_MODELS:
    turns = [t for r in E2 if r["sender"] == m for w, t in r["transcript"] if w in ("receiver", "receiver(readback)")]
    put(f"e2:{SHORT[m]}:voice:hits", str(sum(bool(VOICE.search(t)) for t in turns))); put(f"e2:{SHORT[m]}:voice:turns", f"{len(turns):,}".replace(",", "{,}"))

# total completed episodes behind the paper (Ethics statement), over every result file the tables read
EPI = [f for f in glob.glob("results_frontier_*.jsonl")] + ["results_ablation.jsonl", "results_e2e_dev.jsonl", "results_e2e_heldout.jsonl"]
ntot = sum(not json.loads(l).get("error") for f in EPI for l in open(f)) + sum(not r.get("error") for r in json.load(open("results_claude_sonnet.json")))
put("episodes:total", f"{ntot:,}".replace(",", "{,}"))

with open(os.path.join(HERE, "numbers.tex"), "w") as fh:
    fh.write("% generated by make_tables.py; do not edit. Use \\N{key}.\n")
    for k, val in sorted(NUM.items()): fh.write(f"\\expandafter\\def\\csname n@{k}\\endcsname{{{val}}}\n")
print(f"wrote {len(NUM)} numbers and {len(os.listdir(os.path.join(HERE, 'tables')))} tables")

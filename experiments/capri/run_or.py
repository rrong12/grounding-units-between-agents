"""Same items/conditions as run_claude.py, for open-weight models on OpenRouter (native chat-API multi-turn, as run.py).
Usage: python run_or.py OPENROUTER_MODEL [STEP] [WORKERS]; appends to results_frontier_<short>.jsonl (resumable)."""
import sys, json, os, random, threading, functools
M = sys.argv[1]; step = int(sys.argv[2]) if len(sys.argv) > 2 else 2; workers = int(sys.argv[3]) if len(sys.argv) > 3 else 8
sys.argv = sys.argv[:1]
sys.path.insert(0, os.path.abspath("../../_lib")); import llm
llm.chat = functools.partial(llm.chat, model=M)
import run as R
OUT = f"results_frontier_{M.split('/')[-1]}.jsonl"; LOCK = threading.Lock()


def logged(a):
    r = dict(R.run(a), model=M)
    with LOCK, open(OUT, "a") as fh: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return r


if __name__ == "__main__":
    S = [s for s in json.load(open("sample.json")) if s["kind"] == "implicit" and not (s["concept"] == "price" and s["culture"] == "Iran")][::step]
    conds = ["direct", "none", "card+resolver", "explicit+card+resolver"]
    jobs = [(s, c, 0, False) for s in S for c in conds]
    jobs += [(s, c, 0, True) for s in S[::3] for c in ["none", "explicit+card+resolver"] if not (s["concept"] == "price" and R.conv_unit("price", s["culture"]) not in ("USD", "EUR"))]
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            x = json.loads(l)
            if not x.get("error"): done.add((x["file"], x["cond"], x["same"]))
    jobs = [j for j in jobs if (j[0]["file"], j[1], j[3]) not in done]
    random.Random(0).shuffle(jobs)
    print(M, len(jobs), "jobs", flush=True)
    res = llm.pmap(logged, jobs, workers=workers)
    print("errors:", sum(bool(r.get("error")) for r in res), "of", len(res), flush=True)

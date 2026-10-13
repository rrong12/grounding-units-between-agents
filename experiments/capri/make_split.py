"""Held-out test split for EXPERIMENT_PLAN.md E2: 6 CAPRI implicit-cue chats per culture x concept (speed, distance, price),
drawn only from scaffolds (CAPRI conversation IDs) never used in the development set (sample.json), so no test chat shares a
conversation template with a development chat. Iranian prices are excluded (official vs market FX differ ~10x). CAPRI has no
UK distance chats. Fixed seed; writes heldout.json. Usage: python make_split.py (needs full.json from fetch_capri.py)"""
import json, random, re, collections

PER_CELL, SEED = 6, 0
sid = lambda f: int(re.search(r"ID_(\d+)_", f).group(1))

if __name__ == "__main__":
    F = [f for f in json.load(open("full.json")) if f["kind"] == "implicit" and f["concept"] in ("speed", "distance", "price")]
    dev = [s for s in json.load(open("sample.json")) if s["kind"] == "implicit"]
    dev_ids = {c: {sid(s["file"]) for s in dev if s["concept"] == c} for c in ("speed", "distance", "price")}
    cells = collections.defaultdict(list)
    for f in F:
        if sid(f["file"]) in dev_ids[f["concept"]] or (f["concept"] == "price" and f["culture"] == "Iran"): continue
        cells[(f["concept"], f["culture"])].append(f)
    rng, out = random.Random(SEED), []
    for k in sorted(cells):
        pool = sorted(cells[k], key=lambda f: f["file"]); rng.shuffle(pool); out += pool[:PER_CELL]
    json.dump(out, open("heldout.json", "w"), ensure_ascii=False, indent=1)
    print(len(out), "held-out items in", len(cells), "cells;", collections.Counter(f["concept"] for f in out))

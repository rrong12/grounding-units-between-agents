"""Download the full CAPRI conversation release (yisongmiao/CAPRI on Hugging Face, CC BY 4.0) into capri_full/
and build full.json in the same item format as sample.json (concept, culture, kind, file, conv, conv_type).
Stdlib only; resumable (existing files are skipped). Usage: python fetch_capri.py"""
import json, os, re, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://huggingface.co/api/datasets/yisongmiao/CAPRI/tree/main/"
RAW = "https://huggingface.co/datasets/yisongmiao/CAPRI/resolve/main/"
OUT = "capri_full"
DIRS = [f"conversations/{c}/{k}" for c in ["speed", "distance", "price", "size"] for k in ["implicit", "neutral"]] + \
       [f"conversations/temperature/{v}/{k}" for v in ["camera", "aigen"] for k in ["implicit", "neutral"]]


def get(url, tries=12):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == tries - 1: raise
            time.sleep(min(2 ** i, 120))  # Hugging Face rate limit


def fetch(path):
    dst = os.path.join(OUT, path)
    if not os.path.exists(dst) or os.path.getsize(dst) == 0:
        data = get(RAW + path)  # fetch before opening, so a failed request leaves no empty file
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, "wb").write(data)
    return path


if __name__ == "__main__":
    paths = [x["path"] for d in DIRS for x in json.loads(get(API + d)) if x["type"] == "file" and x["path"].endswith(".json")]
    with ThreadPoolExecutor(2) as ex:
        done = list(ex.map(fetch, paths))
    items = []
    for p in done:
        raw = json.load(open(os.path.join(OUT, p)))
        parts = p.split("/")
        m = re.search(r"_bg_(.+?)_fn_", p)
        items.append({"concept": parts[1], "culture": m.group(1) if m else None, "kind": parts[-2], "file": p,
                      "conv": raw.get("filled_conversation") or raw.get("conversation") or raw["scaffold"]["conversation"],
                      "conv_type": raw.get("conv_type")})
    json.dump(items, open("full.json", "w"), ensure_ascii=False, indent=1)
    print(len(items), "items;", {c: sum(i["concept"] == c and i["kind"] == "implicit" for i in items) for c in ["speed", "distance", "price", "size", "temperature"]})

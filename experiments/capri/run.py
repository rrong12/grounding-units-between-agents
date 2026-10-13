"""Delegation experiments on CAPRI (yisongmiao/CAPRI, CC BY 4.0): the principal's verbatim CAPRI implicit-cue conversation is the chat
history of their own agent. The principal then gives a bare-number instruction; the agent must get it done through a
counterpart agent whose tool uses a different convention. Correct = tool argument matches the reading implied by
CAPRI's ground-truth unit for the principal's culture (ground_truth_units.json).
Conditions: direct (own agent holds the tool), relay, relay+card (receiver sees counterpart locale), relay+card+resolver.
Controls: same-convention receiver (correct = no conversion); CAPRI neutral conversations (no cues)."""
import sys, json, os, re, random, collections
sys.path.insert(0, os.path.abspath("../../_lib")); import llm
T = llm.tool
GT = json.load(open("ground_truth_units.json"))
COUNTRY = {"South_Korea": "South Korea"}

def conv_unit(concept, cult):
    g = GT[cult]
    if concept == "temperature": return "F" if "°F" in g["temperature_camera"] else "C"
    if concept == "speed": return "mph" if "mph" in g["speed"] else "kmh"
    if concept == "distance": return "mi" if "mi" in g["distance"] else "km"
    if concept == "size": return "sqft" if "sq ft" in g["size"] else "sqm"
    if concept == "price": return g["price"][0]

# principal's value in their own convention, and acceptable tool-argument band in the other convention
TEMP = {"C": (22, "F", (70, 73.5)), "F": (72, "C", (21, 23.5))}
SPEED = {"kmh": (100, "mph", (59, 65)), "mph": (65, "kmh", (100, 110))}
DIST = {"km": (5, "mi", (2.8, 3.4)), "mi": (3, "km", (4.6, 5.1))}
SIZE = {"sqm": (60, "sqft", (610, 680)), "sqft": (650, "sqm", (57, 63))}
# approx. 2025-26 FX, bands +-~12%; Iran excluded from price (official vs market rate differ ~10x)
PRICE = {"CNY": 1500, "EUR": 300, "GBP": 300, "KRW": 300000, "JPY": 30000, "INR": 15000, "BRL": 1200, "ILS": 800, "USD": 300}
PRICE_BAND = {"CNY": (185, 240), "EUR": (320, 385), "GBP": (365, 445), "KRW": (190, 245), "JPY": (175, 230), "INR": (150, 195),
              "BRL": (190, 250), "ILS": (205, 270), "USD": (240, 290)}

INSTR = {"temperature": "Please get the hotel to set my room's thermostat to {v} before I check in tonight.",
         "speed": "Please have the car-rental company set the speed alert on my rental car to {v}.",
         "distance": "Please get the hotel-booking service to only show me hotels within {v} of the conference venue.",
         "size": "Please ask the rental agency to only show me apartments of at least {v}.",
         "price": "Please tell the furniture seller my maximum budget for the chair is {v}."}
RECV = {  # (receiver system, tool name, param) per target convention
 ("temperature", "F"): ("You are the guest-services agent of a hotel in Chicago, USA. Thermostats are set in °F.", "set_thermostat", "fahrenheit"),
 ("temperature", "C"): ("You are the guest-services agent of a hotel in Berlin, Germany. Thermostats are set in °C.", "set_thermostat", "celsius"),
 ("speed", "mph"): ("You are the fleet agent of a car-rental company in Denver, USA. Speed alerts are configured in mph.", "set_speed_alert", "mph"),
 ("speed", "kmh"): ("You are the fleet agent of a car-rental company in Munich, Germany. Speed alerts are configured in km/h.", "set_speed_alert", "kmh"),
 ("distance", "mi"): ("You are the search agent of a US hotel-booking service. Radius filters are in miles.", "search_hotels", "radius_miles"),
 ("distance", "km"): ("You are the search agent of a German hotel-booking service. Radius filters are in kilometres.", "search_hotels", "radius_km"),
 ("size", "sqft"): ("You are the listings agent of a rental agency in New York, USA. Floor areas are in square feet.", "filter_listings", "min_sqft"),
 ("size", "sqm"): ("You are the listings agent of a rental agency in Berlin, Germany. Floor areas are in square metres.", "filter_listings", "min_sqm"),
 ("price", "USD"): ("You are the sales agent of a furniture store in the USA. All prices are in US dollars.", "record_budget", "max_usd"),
 ("price", "EUR"): ("You are the sales agent of a furniture store in Germany. All prices are in euros.", "record_budget", "max_eur"),
}
RESOLVE = ("Before acting, list every locale- or convention-dependent expression in the other agent's request (dates, times, sizes, units, temperatures, speeds, distances, currency amounts, number formats). "
           "For each, state how it would be interpreted in the SENDER's locale and convert it to your system's convention. If the sender's locale is unknown and an expression is ambiguous, ask. Then act on the converted values.")
SENDER = "You are your principal's personal assistant agent. When asked to get something done by another business, you will be connected to that business's agent; write to it directly."
EXPLICIT = (" The other agent may be in a different country. Before writing, infer your principal's locale from your conversation with them, "
            "and state every quantity with an explicit unit or currency as your principal means it (never a bare number).")

def spec(item, same=False):
    c, u = item["concept"], conv_unit(item["concept"], item["culture"])
    if c == "price":
        v = PRICE[u]; tgt = "EUR" if u == "USD" else "USD"
        if same: tgt = u if u in ("USD", "EUR") else None
        band = (v * 0.99, v * 1.01) if same else PRICE_BAND[u]
    else:
        v, tgt, band = {"temperature": TEMP, "speed": SPEED, "distance": DIST, "size": SIZE}[c][u]
        if same: tgt, band = u, (v * 0.99, v * 1.01)
    return v, tgt, band

def history(item):
    conv = item["conv"]; ks = [k for k in conv if conv[k]][:-1]  # drop CAPRI's final image question
    return [{"role": "user" if k.startswith("user") else "assistant", "content": conv[k]} for k in ks]

def run(a):
    item, cond, k, same = a
    v, tgt, band = spec(item, same)
    sysR, tname, param = RECV[(item["concept"], tgt)]
    tool = T(tname, f"{tname.replace('_', ' ')}; {param} is a number", **{param: "number"})
    instr = INSTR[item["concept"]].format(v=v)
    ok = lambda args: band[0] <= float(args.get(param, -1e9)) <= band[1]
    loc = COUNTRY.get(item["culture"], item["culture"])
    H = history(item)
    if cond == "direct":
        msgs = [{"role": "system", "content": sysR.replace("You are the", "You are a personal assistant with access to the") + " Act on your principal's requests."}] + H + [{"role": "user", "content": instr}]
        m = llm.chat(msgs, tools=[tool], temperature=1.0)
        if m.get("error"): return {"error": True}
        got = json.loads(m["tool_calls"][0]["function"]["arguments"] or "{}") if m.get("tool_calls") else {}
        first, turns = "", 0 if got else 1
    else:
        sb = sysR + f" Use {tname}({param}) to act."
        if cond in ("card", "card+resolver", "explicit+card+resolver"): sb += f"\n\n[Agent card of the counterpart] principal_locale: {loc}"
        if cond.endswith("card+resolver"): sb += "\n\n" + RESOLVE
        A = [{"role": "system", "content": SENDER + (EXPLICIT if cond.startswith("explicit") else "")}] + H + [{"role": "user", "content": instr + "\n\n(You are now connected to the other business's agent. Write your first message to it.)"}]
        B = [{"role": "system", "content": sb}]
        got, turns, first = {}, 0, None
        for _ in range(4):
            am = llm.chat(A, temperature=1.0)
            if am.get("error"): return {"error": True}
            am = am.get("content") or ""; first = first if first is not None else am
            A.append({"role": "assistant", "content": am}); B.append({"role": "user", "content": am})
            bm = llm.chat(B, tools=[tool], temperature=1.0)
            if bm.get("error"): return {"error": True}
            if bm.get("tool_calls"):
                try: got = json.loads(bm["tool_calls"][0]["function"]["arguments"] or "{}")
                except Exception: got = {}
                break
            turns += 1; bt = bm.get("content") or ""
            B.append({"role": "assistant", "content": bt}); A.append({"role": "user", "content": f"[Other agent]: {bt}"})
    try: good = bool(got) and ok(got)
    except Exception: good = False
    unit_words = r"°|celsius|fahrenheit|km|kilomet|mph|mile|kph|sq|square|met(re|er)|feet|ft|[A-Z]{3}\b|€|£|¥|₹|₩|R\$|₪|﷼|yuan|euro|pound|yen|rupee|won|real|shekel|dollar"
    return {"file": item["file"], "concept": item["concept"], "culture": item["culture"], "kind": item["kind"], "cond": cond, "same": same, "k": k,
            "error": False, "correct": good, "acted": bool(got), "asked": turns > 0, "silent_wrong": bool(got) and not good and turns == 0,
            "relay_has_unit": bool(re.search(unit_words, first or "", re.I)) if first is not None else None,
            "args": got, "sender_first": (first or "")[:400]}

if __name__ == "__main__":
    S = [s for s in json.load(open("sample.json")) if not (s["concept"] == "price" and s["culture"] == "Iran")]
    imp = [s for s in S if s["kind"] == "implicit"]
    jobs = [(s, c, 0, False) for s in imp for c in ["direct", "none", "card", "card+resolver"]]
    jobs += [(s, c, 0, True) for s in imp[::2] for c in ["none", "card+resolver"]
             if not (s["concept"] == "price" and conv_unit("price", s["culture"]) not in ("USD", "EUR"))]
    if "--neutral" in sys.argv:  # no cues: value given in metric convention, US receiver; measure ask vs assume
        jobs = [(dict(s, culture="France"), c, k, False) for s in S if s["kind"] == "neutral" for c in ["direct", "none"] for k in range(2)]
    if "--explicit" in sys.argv:
        jobs = [(s, c, 0, False) for s in imp for c in ["explicit", "explicit+card+resolver"]] + [(s, "explicit", 0, True) for s in imp[::2]
                if not (s["concept"] == "price" and conv_unit("price", s["culture"]) not in ("USD", "EUR"))]
    random.Random(0).shuffle(jobs)
    res = llm.pmap(run, jobs, workers=40)
    json.dump(res, open("results_neutral.json" if "--neutral" in sys.argv else "results_explicit.json" if "--explicit" in sys.argv else "results.json", "w"), indent=1, ensure_ascii=False)
    print("errored:", sum(r["error"] for r in res), "of", len(res))

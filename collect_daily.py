# -*- coding: utf-8 -*-
"""Collect today's RunPod + Vast.ai GPU prices -> data/daily/YYYY-MM-DD.json (UTC date).
Run: python collect_daily.py   (one run per day is enough; same-day reruns overwrite)
"""
import io, json, os, sys, time, math, urllib.parse, urllib.request
from datetime import datetime, timezone
import numpy as np
from models import MODELS

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "data", "daily")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
VAST_CAP = 64  # server returns at most 64 offers per query, regardless of "limit"
SLEEP = 0.6


def runpod_fetch():
    body = json.dumps({"query": "query { gpuTypes { id displayName memoryInGb securePrice communityPrice secureSpotPrice communitySpotPrice } }"}).encode()
    req = urllib.request.Request("https://api.runpod.io/graphql", data=body, headers={**UA, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))["data"]["gpuTypes"]


def price_or_none(v):
    if v is None or v == 0 or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), 4)


def rp_prices(g):
    return {"secure": price_or_none(g.get("securePrice")), "community": price_or_none(g.get("communityPrice")),
            "secure_spot": price_or_none(g.get("secureSpotPrice")), "community_spot": price_or_none(g.get("communitySpotPrice"))}


def vast_query(q):
    u = "https://console.vast.ai/api/v0/bundles/?q=" + urllib.parse.quote(json.dumps(q))
    for attempt in range(3):
        try:
            time.sleep(SLEEP)
            return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60))["offers"]
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3)


def vast_fetch(name, typ, warnings):
    """All rentable offers for gpu_name/type. Query cap is 64 -> bisect on dph_total (machine price);
    if many offers share one price, additionally split by num_gpus."""
    found = {}
    gpu_splits = [{"eq": 1}, {"eq": 2}, {"gte": 3, "lte": 4}, {"gte": 5, "lte": 8}, {"gt": 8}]

    def rec(lo, hi, depth, ng):
        q = {"gpu_name": {"eq": name}, "rentable": {"eq": True}, "type": typ, "limit": 10000,
             "dph_total": {"gt": lo, "lte": hi}}
        if ng:
            q["num_gpus"] = ng
        offers = vast_query(q)
        for o in offers:
            found[o["id"]] = o
        if len(offers) < VAST_CAP:
            return
        prices = sorted(o["dph_total"] for o in offers)
        mid = prices[len(prices) // 2]
        if depth < 14 and lo < mid < hi:
            rec(lo, mid, depth + 1, ng)
            rec(mid, hi, depth + 1, ng)
        elif ng is None:  # many identical prices: split by GPU count instead
            for g in gpu_splits:
                rec(lo, hi, depth + 1, g)
        else:
            warnings.append(f"vast {name}/{typ}: range ({lo},{hi}] num_gpus={ng} still capped at {VAST_CAP}; possibly incomplete")

    rec(0.0, 2000.0, 0, None)
    return list(found.values())


def vast_summary(offers, min_vram_gb=None):
    per_gpu, gpus = [], 0
    for o in offers:
        n = o.get("num_gpus") or 1
        if min_vram_gb and (o.get("gpu_ram") or 0) / 1024.0 < min_vram_gb:
            continue
        per_gpu.append(o["dph_total"] / n)
        gpus += n
    if not per_gpu:
        return {"offer_count": 0, "gpu_count": 0, "min": None, "p25": None, "median": None, "p75": None}
    a = np.array(per_gpu, dtype=float)
    return {"offer_count": len(per_gpu), "gpu_count": gpus, "min": round(float(a.min()), 4),
            "p25": round(float(np.percentile(a, 25)), 4), "median": round(float(np.median(a)), 4),
            "p75": round(float(np.percentile(a, 75)), 4)}


def main():
    now = datetime.now(timezone.utc)
    result = {"captured_at": now.isoformat(timespec="seconds"), "date": now.strftime("%Y-%m-%d"),
              "notes": {
                  "runpod": "api.runpod.io/graphql gpuTypes; USD per GPU-hour; price 0/null = not offered -> null. Headline = primary variant per model; others in runpod_variants.",
                  "vast": "console.vast.ai bundles; per-GPU = dph_total/num_gpus; each machine offer counted once; server cap 64/query so queried by price bisection. bid = interruptible.",
              },
              "errors": [], "warnings": [], "models": {}}
    rp = None
    try:
        rp = {g["id"]: g for g in runpod_fetch()}
    except Exception as e:
        result["errors"].append(f"runpod: {e!r}")
    for key, m in MODELS.items():
        entry = {"runpod": None, "runpod_variants": {}, "vast": {"on_demand": None, "bid": None}}
        if rp is not None:
            g = rp.get(m["runpod_primary"])
            if g:
                entry["runpod"] = rp_prices(g)
            else:
                result["warnings"].append(f"runpod id not found: {m['runpod_primary']}")
            for vid in m["runpod_variants"]:
                if vid in rp:
                    entry["runpod_variants"][vid] = rp_prices(rp[vid])
        for typ, field in (("on-demand", "on_demand"), ("bid", "bid")):
            if not m["vast_names"]:
                continue
            offers = []
            try:
                for name in m["vast_names"]:
                    offers += vast_fetch(name, typ, result["warnings"])
                entry["vast"][field] = vast_summary(offers, m.get("vast_min_vram_gb"))
            except Exception as e:
                result["errors"].append(f"vast {key}/{typ}: {e!r}")
        result["models"][key] = entry
        print("done", key, flush=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, result["date"] + ".json")
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("wrote", path, "errors:", result["errors"], "warnings:", result["warnings"])


if __name__ == "__main__":
    sys.exit(main())

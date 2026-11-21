# -*- coding: utf-8 -*-
"""Build site/gpu_data.json (front-end data) from GetDeploying weekly CSV + our daily snapshots + stock prices.
Run: python build_data.py            (downloads weekly.csv fresh, falls back to cache if download fails)
"""
import io, json, math, os, sys, glob, urllib.request
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from models import MODELS, ATTRIBUTION, STOCKS, STOCK_START

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data", "cache", "weekly.csv")
DAILY_DIR = os.path.join(HERE, "data", "daily")
OUT = os.path.join(HERE, "site", "gpu_data.json")
CSV_URL = "https://getdeploying.com/dataset/gpu-prices/weekly.csv"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
REGIME_THRESHOLD_PCT = 2.0  # |change| below this counts as flat -> "mixed"


def clean(v, nd=3):
    """NaN/None -> None, numpy -> python, round."""
    if v is None:
        return None
    try:
        if isinstance(v, (float, np.floating)) and (math.isnan(v) or math.isinf(v)):
            return None
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return round(float(v), nd)
    return v


def load_weekly():
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    try:
        req = urllib.request.Request(CSV_URL, headers=UA)
        data = urllib.request.urlopen(req, timeout=90).read()
        with open(CACHE, "wb") as f:
            f.write(data)
        src = "downloaded"
    except Exception as e:
        print("WARN download failed, using cache:", e)
        src = "cache"
    df = pd.read_csv(CACHE)
    df["date"] = pd.to_datetime(df["date"])
    return df, src


def pct(a, b):
    """% change from b to a."""
    if a is None or b is None or pd.isna(a) or pd.isna(b) or b == 0:
        return None
    return (a / b - 1) * 100


def asof(series, date):
    """value at last index <= date, with the matching timestamp."""
    s = series.dropna()
    s = s[s.index <= date]
    if s.empty:
        return None, None
    return s.iloc[-1], s.index[-1]


def decay_annualized(s):
    """log-linear regression of price vs time (years) -> annualized % change."""
    s = s.dropna()
    s = s[s > 0]
    if len(s) < 8:
        return None
    t = (s.index - s.index[0]).days.values / 365.25
    slope = np.polyfit(t, np.log(s.values), 1)[0]
    return (math.exp(slope) - 1) * 100


def build_weekly(df, slug_list):
    sub = df[df.gpu_slug.isin(slug_list)]
    od = sub[sub.billing_type == "ON_DEMAND"].set_index("date").sort_index()
    sp = sub[sub.billing_type == "SPOT"].set_index("date").sort_index()
    rs = sub[(sub.billing_type == "RESERVATION") & (sub.reservation_months == 1)].set_index("date").sort_index()
    if od.index.duplicated().any():  # only if several slugs are merged
        od = od.groupby(level=0).median()
    w = pd.DataFrame(index=od.index)
    w["on_demand_median"] = od["median_price"]
    w["on_demand_min"] = od["min_price"]
    w["spot_median"] = sp["median_price"].reindex(w.index)
    w["reservation_1m_median"] = rs["median_price"].reindex(w.index) if not rs.empty else np.nan
    w["provider_count"] = od["provider_count"]
    w["offering_count"] = od["offering_count"]
    return w


def derive(w):
    d = {}
    p = w["on_demand_median"]
    last = w.index[-1]
    d["latest_week"] = last.strftime("%Y-%m-%d")
    d["latest_on_demand_median"] = clean(p.iloc[-1])
    last52 = p[p.index > last - pd.Timedelta(weeks=52)]
    d["decay_annualized_52w_pct"] = clean(decay_annualized(last52), 1)
    d["decay_annualized_since_first_pct"] = clean(decay_annualized(p), 1)
    d["first_week"] = w.index[0].strftime("%Y-%m-%d")
    for n in (4, 13, 52):
        base, ts = asof(p, last - pd.Timedelta(weeks=n))
        d[f"price_change_{n}w_pct"] = clean(pct(p.iloc[-1], base), 1) if base is not None else None
    d["price_change_26w_pct"] = clean(pct(p.iloc[-1], asof(p, last - pd.Timedelta(weeks=26))[0]), 1)
    # supply: 3-week mean to damp single-week noise
    def m3(col, end):
        s = w[col].dropna()
        s = s[s.index <= end].iloc[-3:]
        return s.mean() if len(s) else None
    end_ago = last - pd.Timedelta(weeks=13)

    def unreliable(row):
        """spot median above on-demand median in that week -> spot sample unreliable."""
        sm, om = row.get("spot_median"), row.get("on_demand_median")
        return bool(pd.notna(sm) and pd.notna(om) and om and sm > om)

    def window(end_ts, n):
        """raw (unrounded) numbers for window n ending at row end_ts (same method as the page)."""
        tgt = end_ts - pd.Timedelta(weeks=n)
        base, _ = asof(p, tgt)
        pr = pct(p[end_ts], base) if base is not None else None
        offc = pct(m3("offering_count", end_ts), m3("offering_count", tgt))
        prov = pct(m3("provider_count", end_ts), m3("provider_count", tgt))
        pv = p.dropna()
        pv = pv[pv.index <= tgt]
        brow = w.loc[pv.index[-1]] if len(pv) else None
        bad, sa = False, None
        if brow is not None and pd.notna(brow["spot_median"]) and brow["on_demand_median"]:
            if unreliable(brow):
                bad = True
            else:
                sa = (1 - brow["spot_median"] / brow["on_demand_median"]) * 100
        return pr, offc, prov, sa, bad

    def regime_of(pr, oc):
        if pr is None or oc is None or abs(pr) < REGIME_THRESHOLD_PCT or abs(oc) < REGIME_THRESHOLD_PCT:
            return "mixed"
        if pr < 0 and oc > 0:
            return "loosening"
        if pr > 0 and oc < 0:
            return "tightening"
        if pr > 0 and oc > 0:
            return "demandUp"
        return "demandDown"

    regs = {}
    for n in (4, 13, 26):
        pr, oc, pv_, sa, bad = window(last, n)
        if n != 52:
            d[f"offering_change_{n}w_pct"] = clean(oc, 1)
            d[f"provider_change_{n}w_pct"] = clean(pv_, 1)
        d[f"spot_unreliable_{n}w_ago"] = bad
        if n != 13:
            d[f"spot_discount_{n}w_ago_pct"] = clean(sa, 1)
        regs[n] = regime_of(pr, oc)
        d[f"regime_{n}w"] = regs[n]
    d["supply_regime"] = regs[13]
    d["spot_unreliable_latest"] = unreliable(w.iloc[-1])
    # early warning: 4w regime not mixed, differs from 13w, and held the same one week earlier
    ew = None
    if len(w) >= 2:
        pr_prev, oc_prev, _, _, _ = window(w.index[-2], 4)
        prev4 = regime_of(pr_prev, oc_prev)
        if regs[4] != "mixed" and regs[4] != regs[13] and prev4 == regs[4]:
            ew = {"r4": regs[4], "r13": regs[13]}
    d["early_warning"] = ew
    # spot discount
    def disc(date):
        o, _ = asof(w["on_demand_median"], date)
        s, _ = asof(w["spot_median"], date)
        return clean((1 - s / o) * 100, 1) if o and s is not None and not pd.isna(s) else None
    d["spot_discount_latest_pct"] = disc(last)
    d["spot_discount_13w_ago_pct"] = disc(end_ago)
    # data quality flags
    tail = w.tail(13)
    d["min_provider_count_13w"] = clean(tail["provider_count"].min())
    d["repeated_value_weeks"] = int((p.diff() == 0).sum())
    return d


def series_rows(w):
    rows = []
    for ts, r in w.iterrows():
        rows.append({"date": ts.strftime("%Y-%m-%d"),
                     "on_demand_median": clean(r["on_demand_median"]), "on_demand_min": clean(r["on_demand_min"]),
                     "spot_median": clean(r["spot_median"]), "reservation_1m_median": clean(r["reservation_1m_median"]),
                     "provider_count": clean(r["provider_count"]), "offering_count": clean(r["offering_count"])})
    return rows


def load_daily():
    snaps = []
    for fp in sorted(glob.glob(os.path.join(DAILY_DIR, "*.json"))):
        with io.open(fp, encoding="utf-8") as f:
            snaps.append(json.load(f))
    return snaps


def daily_rows(snaps, key):
    rows = []
    for s in snaps:
        m = (s.get("models") or {}).get(key) or {}
        rp = m.get("runpod") or {}
        v = m.get("vast") or {}
        od, bid = v.get("on_demand") or {}, v.get("bid") or {}
        rows.append({"date": s["date"], "runpod_secure": clean(rp.get("secure")), "runpod_community": clean(rp.get("community")),
                     "vast_on_demand_median": clean(od.get("median")), "vast_on_demand_gpu_count": clean(od.get("gpu_count")),
                     "vast_on_demand_offer_count": clean(od.get("offer_count")), "vast_bid_median": clean(bid.get("median"))})
    return rows


def fetch_stocks(warnings):
    import yfinance as yf
    out = {}
    for t in STOCKS:
        try:
            h = yf.download(t, start=STOCK_START, interval="1d", auto_adjust=True, progress=False)
            if h is None or h.empty:
                warnings.append(f"stock {t}: empty")
                continue
            c = h["Close"]
            if isinstance(c, pd.DataFrame):
                c = c.iloc[:, 0]
            c = c.dropna()
            c.index = pd.to_datetime(c.index).tz_localize(None)
            first = c.index[0]
            if t not in ("CRWV", "NBIS") and first > pd.Timestamp(STOCK_START) + pd.Timedelta(days=10):
                warnings.append(f"stock {t}: history starts {first.date()} (requested {STOCK_START}) - possibly truncated")
            if t in ("CRWV", "NBIS"):
                warnings.append(f"stock {t}: first date {first.date()} (late listing: CRWV 2025-03, NBIS 2024-10; expected)")
            # weekly: close on/before each Monday
            mondays = pd.date_range(first - pd.Timedelta(days=first.weekday()), c.index[-1], freq="W-MON")
            wk = []
            for mday in mondays:
                v, ts = asof(c, mday)
                if v is not None:
                    wk.append({"date": mday.strftime("%Y-%m-%d"), "close": clean(v, 2)})
            last_d = c.index[-1]
            dl = c[c.index > last_d - pd.Timedelta(days=120)]
            out[t] = {"first_date": first.strftime("%Y-%m-%d"), "last_date": last_d.strftime("%Y-%m-%d"),
                      "weekly": wk, "daily": [{"date": i.strftime("%Y-%m-%d"), "close": clean(v, 2)} for i, v in dl.items()]}
        except Exception as e:
            warnings.append(f"stock {t}: {e!r}")
    return out


def main():
    warnings = []
    df, src = load_weekly()
    snaps = load_daily()
    weekly, daily, derived, models_meta = {}, {}, {}, []
    for key, m in MODELS.items():
        w = build_weekly(df, m["getdeploying"])
        if w.empty:
            warnings.append(f"{key}: no GetDeploying rows")
            continue
        weekly[key] = series_rows(w)
        derived[key] = derive(w)
        daily[key] = daily_rows(snaps, key)
        models_meta.append({"key": key, "label": m["label"], "vram_gb": m["vram_gb"], "launch": m["launch"],
                            "launch_note": m["launch_note"], "merge_note": m["merge_note"],
                            "mapping": {"getdeploying": m["getdeploying"], "runpod_primary": m["runpod_primary"],
                                        "runpod_variants": m["runpod_variants"], "vast_names": m["vast_names"]}})
        if derived[key]["min_provider_count_13w"] is not None and derived[key]["min_provider_count_13w"] < 5:
            warnings.append(f"{key}: fewer than 5 providers in some of last 13 weeks")
    stocks = fetch_stocks(warnings)
    data = {
        "meta": {
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "attribution": ATTRIBUTION,
            "weekly_range": [df.date.min().strftime("%Y-%m-%d"), df.date.max().strftime("%Y-%m-%d")],
            "weekly_source_status": src,
            "daily_snapshots": [s["date"] for s in snaps],
            "sources": {
                "getdeploying": "Weekly median of daily captures (ON_DEMAND, SPOT, 1-month RESERVATION). CC BY 4.0. USD per GPU-hour. Series starts 2025-11-17 for the tracked models.",
                "runpod": "Public GraphQL gpuTypes (own daily snapshots).",
                "vast": "Vast.ai marketplace offers, per-GPU = dph_total/num_gpus (own daily snapshots).",
                "stocks": "yfinance, split/dividend-adjusted daily closes; weekly = last close on/before Monday.",
            },
            "models": models_meta,
            "method": {
                "decay": "annualized % = exp(slope of OLS ln(on_demand_median) vs years)-1; 52w window and since first week.",
                "supply": "Windows 4/13/26 weeks. price_change_Nw = on-demand median vs N weeks earlier; offering/provider_change_Nw = pct change of 3-week-mean counts. 5 regime labels per window (regime_Nw): |price| or |offering| < " + str(REGIME_THRESHOLD_PCT) + " pct (unrounded) = mixed; price down + offering up = loosening; price up + offering down = tightening; both up = demandUp; both down = demandDown. supply_regime = regime_13w. Early warning (early_warning): 4w regime not mixed, differs from 13w regime, and the 4w regime one week earlier is the same.",
                "spot_discount": "(1 - spot_median/on_demand_median)*100 at latest week and N weeks earlier. Spot-unreliable rule: a week whose spot median > on-demand median is unreliable (spot_unreliable_latest / spot_unreliable_Nw_ago; page shows it as not comparable).",
            },
            "warnings": warnings,
        },
        "weekly": weekly, "daily": daily, "stocks": stocks, "derived": derived,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("wrote", OUT, os.path.getsize(OUT), "bytes")
    for w_ in warnings:
        print("WARN", w_)


if __name__ == "__main__":
    sys.exit(main())

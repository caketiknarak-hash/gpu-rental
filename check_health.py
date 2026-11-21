"""Health check run by the daily workflow after build_data.py.
Exit 1 (job fails -> GitHub emails the owner) when the data the page shows is incomplete or stale.
The data that was collected is still committed and published before this check runs."""
import io, json, os, sys
from datetime import datetime, timezone, timedelta

WEEKLY_MAX_AGE_DAYS = 10
DAILY_MAX_AGE_DAYS = 2

def main():
    problems = []
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    snap = os.path.join("data", "daily", today + ".json")
    if not os.path.exists(snap):
        problems.append(f"daily snapshot {today} missing")
    else:
        with io.open(snap, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("errors"):
            problems.append(f"daily snapshot {today} has errors: {d['errors']}")
    with io.open(os.path.join("site", "gpu_data.json"), encoding="utf-8") as f:
        meta = json.load(f)["meta"]
    if meta.get("weekly_source_status") != "downloaded":
        problems.append(f"GetDeploying weekly CSV not downloaded (status={meta.get('weekly_source_status')})")
    last_week = datetime.strptime(meta["weekly_range"][1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if now - last_week > timedelta(days=WEEKLY_MAX_AGE_DAYS):
        problems.append(f"GetDeploying weekly data stale: last week {meta['weekly_range'][1]}")
    snaps = meta.get("daily_snapshots") or []
    if not snaps or now - datetime.strptime(snaps[-1], "%Y-%m-%d").replace(tzinfo=timezone.utc) > timedelta(days=DAILY_MAX_AGE_DAYS):
        problems.append(f"daily data stale: last snapshot {snaps[-1] if snaps else 'none'}")
    for w in meta.get("warnings") or []:
        print("warning:", w)
    if problems:
        for p in problems:
            print("::error::" + p)
        sys.exit(1)
    print("health ok")

if __name__ == "__main__":
    main()

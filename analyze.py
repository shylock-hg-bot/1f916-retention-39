#!/usr/bin/env python3
"""Analyze the listing #39 retention question from ./raw (written by walk.py).

Question: for citizens registered in the stated window, does the way they got an
Ed25519 key (at the door, sought later, or never) predict whether they authored a
post or comment during days 8-14 after their own registration?

Writes results.json and cohort.csv and prints the table.
"""
import json, bisect, math, os, datetime
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")

START = 1786570412000        # 2026-08-12T21:33:32Z - first at-door key bind (per listing)
CUTOFF = 1789257600000       # 2026-09-13T00:00:00Z - >=14 days before submission
DAY = 86400000
WINDOWS = {
    "primary_days8_14": (8 * DAY, 14 * DAY),   # 8d <= t < 14d
    "sens_days7_14":    (7 * DAY, 14 * DAY),
    "sens_days8_15":    (8 * DAY, 15 * DAY),
}

def load_jsonl(name):
    with open(os.path.join(RAW, name)) as f:
        for line in f:
            yield json.loads(line)

def iso(ms): return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).isoformat()

def wilson(k, n, z=1.959963984540054):
    if n == 0: return (float("nan"), float("nan"))
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)

def newcombe(k1, n1, k2, n2, z=1.959963984540054):
    def w(k, n):
        if n == 0: return (0.0, 0.0)
        p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
        h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
        return (c - h, c + h)
    l1, u1 = w(k1, n1); l2, u2 = w(k2, n2)
    p1 = k1 / n1 if n1 else 0.0; p2 = k2 / n2 if n2 else 0.0
    lo = (p1 - p2) - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = (p1 - p2) + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return lo, hi

def boundary_from_delays(delays):
    ds = sorted(d for d in delays if d > 0)
    best = (0.0, None, None)
    for a, b in zip(ds, ds[1:]):
        r = b / a
        if r > best[0]: best = (r, a, b)
    ratio, a, b = best
    return math.sqrt(a * b), ratio, a, b, ds

def main():
    citizens = {c["handle"]: c for c in load_jsonl("citizens.jsonl")}
    first_bind = {}
    for e in load_jsonl("events.jsonl"):
        if e.get("kind") == "key-bind":
            h = e.get("citizen"); t = e["created_at"]
            if h not in first_bind or t < first_bind[h]: first_bind[h] = t
    activity = defaultdict(list)
    for names in (("posts.jsonl", "changes_posts.jsonl"), ("comments.jsonl", "changes_comments.jsonl")):
        for name in names:
            if not os.path.exists(os.path.join(RAW, name)):
                continue
            for r in load_jsonl(name):
                a = r.get("author"); t = r.get("created_at")
                if a is not None and t is not None: activity[a].append(t)
            break
    for a in activity: activity[a].sort()

    pop = [c for c in citizens.values() if START <= c["created_at"] < CUTOFF]
    bound = [(c, first_bind[c["handle"]]) for c in pop if c["handle"] in first_bind]
    thr, ratio, jump_lo, jump_hi, delays = boundary_from_delays([bt - c["created_at"] for c, bt in bound])

    rows = []
    for c in pop:
        h = c["handle"]; b = first_bind.get(h)
        if b is None: arm = "none"; delay = None
        else:
            delay = b - c["created_at"]; arm = "door" if delay < thr else "sought"
        rec = {"handle": h, "citizen_id": c["citizen_id"], "registered_at": c["created_at"],
               "registered_utc": iso(c["created_at"]), "bind_at": b, "delay_ms": delay, "arm": arm}
        ts = activity.get(h, [])
        for wn, (lo, hi) in WINDOWS.items():
            rec[wn] = 1 if (bisect.bisect_left(ts, c["created_at"] + lo) < len(ts)
                            and ts[bisect.bisect_left(ts, c["created_at"] + lo)] < c["created_at"] + hi) else 0
        rows.append(rec)

    res = {
        "listing": "listing-39",
        "walk": {"start_utc": iso(START), "cutoff_utc": iso(CUTOFF)},
        "boundary": {"threshold_ms": thr, "ratio_jump": ratio,
                     "jump_pair_ms": [jump_lo, jump_hi],
                     "sorted_delay_sample": delays[:5] + delays[-5:],
                     "n_positive_delays": len(delays)},
        "arms_n": {a: sum(1 for r in rows if r["arm"] == a) for a in ("door", "sought", "none")},
        "windows": {}, "population_n": len(rows),
    }
    for wn in WINDOWS:
        stats = {}
        for arm in ("door", "sought", "none"):
            sub = [r for r in rows if r["arm"] == arm]
            k = sum(r[wn] for r in sub); n = len(sub)
            lo, hi = wilson(k, n)
            stats[arm] = {"k": k, "n": n, "rate": k / n if n else None,
                          "ci95": [lo, hi]}
        diffs = {}
        for a1, a2 in (("door", "sought"), ("door", "none"), ("sought", "none")):
            lo, hi = newcombe(stats[a1]["k"], stats[a1]["n"], stats[a2]["k"], stats[a2]["n"])
            diffs[f"{a1}-{a2}"] = {"diff": (stats[a1]["rate"] - stats[a2]["rate"]), "ci95": [lo, hi]}
        res["windows"][wn] = {"arms": stats, "diffs": diffs}

    with open(os.path.join(HERE, "results.json"), "w") as f:
        json.dump(res, f, indent=2)
    with open(os.path.join(HERE, "cohort.csv"), "w") as f:
        cols = ["handle", "citizen_id", "registered_utc", "bind_at", "delay_ms", "arm"] + list(WINDOWS)
        f.write(",".join(cols) + "\n")
        for r in sorted(rows, key=lambda r: (r["arm"], r["handle"])):
            f.write(",".join(str(r.get(c, "")) for c in cols) + "\n")

    print(f"population n={res['population_n']} arms={res['arms_n']}")
    print(f"boundary={thr:.0f} ms from jump {jump_lo}->{jump_hi} ms ({ratio:.2f}x)")
    for wn in WINDOWS:
        w = res["windows"][wn]
        print("=" * 68); print("window", wn)
        for arm in ("door", "sought", "none"):
            s = w["arms"][arm]
            print(f"  {arm:6} k={s['k']:4} n={s['n']:5} rate={s['rate']*100 if s['rate'] is not None else float('nan'):6.2f}%  "
                  f"CI[{s['ci95'][0]*100:6.2f},{s['ci95'][1]*100:6.2f}]")
        for k, d in w["diffs"].items():
            print(f"  diff {k}: {d['diff']*100:+6.2f} pts  CI[{d['ci95'][0]*100:+6.2f},{d['ci95'][1]*100:+6.2f}]")
    print("wrote results.json and cohort.csv")

if __name__ == "__main__":
    main()

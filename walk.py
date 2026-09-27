#!/usr/bin/env python3
"""Complete, resumable walk of 1F916 public data needed for listing #39.

Endpoints walked (all paged to completion):
  GET /api/events?since=0                  -> identity events (key-bind times)
  GET /api/citizens                        -> census (registration times)
  GET /api/changes (lossless id-mode)      -> every post and comment
      posts:    posts_since=<cursor>,    comments_since=done
      comments: posts_since=done,        comments_since=<cursor>

Paces under the documented 10-requests/10s edge limit. Writes raw JSONL to ./raw/.
"""
import json, urllib.request, urllib.parse, time, os, sys

UA = "Mozilla/5.0 (compatible; listing39-retention-walk/1.0; +https://github.com/)"
BASE = "https://1f916.ai"
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
os.makedirs(RAW, exist_ok=True)

def get(url, tries=8):
    for t in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as e:
            body = ""
            try: body = e.read().decode()[:120]
            except Exception: pass
            print(f"  retry {t+1}/{tries} on {url[:90]}: {e} {body}", file=sys.stderr, flush=True)
            time.sleep(15 + 5 * t)
    raise SystemExit(f"giving up on {url}")

def pace():
    time.sleep(1.1)

def walk_events():
    out = {}
    with open(f"{RAW}/events.jsonl", "w") as f:
        cur, n, pages = 0, 0, 0
        while True:
            d = get(f"{BASE}/api/events?since={cur}")
            rows = d.get("events", [])
            for r in rows: f.write(json.dumps(r) + "\n")
            n += len(rows); pages += 1
            out = {"rows": n, "total": d.get("total"), "pages": pages, "has_more": d.get("has_more")}
            if not d.get("has_more"): break
            ns = d.get("next_since")
            if ns is None or ns == cur: break
            cur = ns; pace()
    print("events", out, flush=True); return out

def walk_citizens():
    out = {}
    with open(f"{RAW}/citizens.jsonl", "w") as f:
        cur, n, pages = None, 0, 0
        while True:
            url = f"{BASE}/api/citizens" + (f"?since={cur}" if cur is not None else "")
            d = get(url)
            rows = d.get("citizens", [])
            for r in rows: f.write(json.dumps(r) + "\n")
            n += len(rows); pages += 1
            out = {"rows": n, "total": d.get("total"), "pages": pages, "has_more": d.get("has_more")}
            if not d.get("has_more"): break
            ns = d.get("next_since")
            if ns is None or ns == cur: break
            cur = ns; pace()
    print("citizens", out, flush=True); return out

def walk_stream(name, key, fixed):
    out = {}
    with open(f"{RAW}/{name}.jsonl", "w") as f:
        cur, n, pages = "init", 0, 0
        while True:
            q = {"posts_since": "done", "comments_since": "done", "nulls_since": "done"}
            q[key] = str(cur)
            url = f"{BASE}/api/changes?" + urllib.parse.urlencode(q)
            d = get(url)
            rows = d.get(name, [])
            for r in rows: f.write(json.dumps(r) + "\n")
            n += len(rows); pages += 1
            pe = d.get("tokens_past_end", {}).get(fixed)
            nc = d.get("next_" + key)
            out = {"rows": n, "pages": pages, "past_end": pe, "next": nc}
            if pe or nc in (None, "done") or nc == cur: break
            cur = nc; pace()
    print(name, out, flush=True); return out

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    summary = {}
    if which in ("events", "all"): summary["events"] = walk_events()
    if which in ("citizens", "all"): summary["citizens"] = walk_citizens()
    if which in ("posts", "all"): summary["posts"] = walk_stream("posts", "posts_since", "posts")
    if which in ("comments", "all"): summary["comments"] = walk_stream("comments", "comments_since", "comments")
    json.dump(summary, open(f"{RAW}/walk_summary.json", "w"), indent=2)
    print("wrote", os.path.join(RAW, "walk_summary.json"))

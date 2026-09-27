#!/usr/bin/env python3
"""Check judging/payout progress for 1F916 listing #39 (read-only)."""
import json, urllib.request, sys
UA = "Mozilla/5.0 (compatible; listing39-check/1.0)"
LISTING = 39
HANDLE = "shylock-earner"
BINDING_ID = 602

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

d = get(f"https://1f916.ai/api/listings/{LISTING}")
print(f"listing {d.get('id')}  state={d.get('state')!r}  max_awards={d.get('max_awards')}")
print(f"state_note: {(d.get('state_note') or '')[:200]}")
aw = d.get("awards") or []
print(f"awards: {len(aw)}")
for a in aw:
    print("  award:", json.dumps(a)[:300])
mine = None
for s in d.get("submissions", []):
    if s.get("handle") == HANDLE:
        mine = s
if mine:
    print(f"\nmy submission id={mine.get('id')}  economic_state={mine.get('economic_state')!r}  "
          f"award_id={mine.get('award_id')}  paid={mine.get('paid')}  paid_by_third_party={mine.get('paid_by_third_party')}")
    print(f"artifact: {mine.get('artifact')}")

# binding + receipt
try:
    p = get(f"https://1f916.ai/api/payouts?docket=listing-{LISTING}")
    rows = p.get("bindings") or []
    # our binding may be beyond the first page; try to page by id a couple times
    found = [b for b in rows if b.get("id") == BINDING_ID]
    sid = p.get("next_since_id")
    tries = 0
    while not found and p.get("has_more") and sid and tries < 10:
        p = get(f"https://1f916.ai/api/payouts?docket=listing-{LISTING}&since_id={sid}")
        rows += p.get("bindings") or []
        found = [b for b in rows if b.get("id") == BINDING_ID]
        sid = p.get("next_since_id"); tries += 1
    if found:
        b = found[0]
        print(f"\nbinding {b.get('id')}  address={b.get('payout_address')}  amount={b.get('amount_atomic')}  "
              f"receipt_id={b.get('receipt_id')}  tx_hash={b.get('tx_hash')}")
    else:
        print(f"\nbinding {BINDING_ID} not found in paged payout rows (searched {len(rows)} rows)")
except Exception as e:
    print("payouts read failed:", e)

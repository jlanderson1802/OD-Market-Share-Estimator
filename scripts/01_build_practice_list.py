#!/usr/bin/env python3
# Build a practice list using Yelp first, then (optionally) Google Places Text Search as a top-up,
# with budget/call caps to keep costs low.
# Writes data/practices.csv with columns: id,name,website,phone,address,source
import csv, time, json, sys, argparse, math
from pathlib import Path
import requests

def load_config(path):
  import yaml
  with open(path, "r", encoding="utf-8") as f:
    return yaml.safe_load(f)

def yelp_get_business_details(session, api_key, business_id):
  """Fetch business details to get actual website URL"""
  url = f"https://api.yelp.com/v3/businesses/{business_id}"
  headers = {"Authorization": f"Bearer {api_key}"}
  try:
    r = session.get(url, headers=headers, timeout=20)
    if r.status_code == 200:
      return r.json()
  except:
    pass
  return {}

def yelp_city(session, api_key, city, limit=200, remaining_calls=None):
  out = []
  url = "https://api.yelp.com/v3/businesses/search"
  headers = {"Authorization": f"Bearer {api_key}"}
  params = {"term": "dentist", "location": city, "limit": 50, "offset": 0}
  calls_used = 0
  while len(out) < limit and (remaining_calls is None or calls_used < remaining_calls):
    r = session.get(url, headers=headers, params=params, timeout=20)
    calls_used += 1
    js = r.json()
    for b in js.get("businesses", []):
      # Fetch business details to get actual website
      business_id = b.get("id", "")
      website = ""
      if business_id and (remaining_calls is None or calls_used < remaining_calls):
        details = yelp_get_business_details(session, api_key, business_id)
        calls_used += 1
        website = details.get("url", "")  # Yelp business page as fallback
        # Check if there's an actual website in the details
        if details:
          website = details.get("url", "")

      out.append({
        "name": b.get("name",""),
        "address": ", ".join(filter(None, [
            b.get("location",{}).get("address1",""),
            b.get("location",{}).get("city",""),
            b.get("location",{}).get("state",""),
        ])),
        "website": website,
        "phone": b.get("display_phone",""),
        "source": "yelp"
      })
      if len(out) >= limit:
        return out, calls_used
    if not js.get("businesses") or len(js.get("businesses")) < 50:
      break
    params["offset"] += 50
  return out, calls_used

def google_get_place_details(session, api_key, place_id):
  """Fetch place details to get website and phone"""
  url = "https://maps.googleapis.com/maps/api/place/details/json"
  params = {"place_id": place_id, "fields": "website,formatted_phone_number", "key": api_key}
  try:
    r = session.get(url, params=params, timeout=20)
    if r.status_code == 200:
      return r.json().get("result", {})
  except:
    pass
  return {}

def google_places_city(session, api_key, city, limit=200, remaining_calls=10):
  """Fetch via Places Text Search + Place Details for websites. Returns list and the number of API calls used.
  Each request (including next_page_token fetches and place details) is counted as one call.
  remaining_calls: how many Google calls we're allowed to make.
  """
  out = []
  url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
  params = {"query": f"dentist in {city}", "key": api_key}
  calls_used = 0

  while True:
    if remaining_calls is not None and calls_used >= remaining_calls:
      break
    r = session.get(url, params=params, timeout=20)
    calls_used += 1
    data = r.json()
    for res in data.get("results", []):
      # Fetch place details to get actual website
      place_id = res.get("place_id", "")
      website = ""
      phone = ""
      if place_id and (remaining_calls is None or calls_used < remaining_calls):
        details = google_get_place_details(session, api_key, place_id)
        calls_used += 1
        website = details.get("website", "")
        phone = details.get("formatted_phone_number", "")

      out.append({
        "name": res.get("name",""),
        "address": res.get("formatted_address",""),
        "website": website,
        "phone": phone,
        "source": "google_places"
      })
      if len(out) >= limit:
        return out, calls_used
    tok = data.get("next_page_token")
    if not tok or len(out) >= limit:
      break
    time.sleep(2)  # per Google guidance
    params = {"pagetoken": tok, "key": api_key}
  return out, calls_used

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--seeds", required=True, help="CSV with column 'city'")
  ap.add_argument("--out", required=True, help="Output CSV path")
  ap.add_argument("--config", required=True, help="config.yaml with API keys + optional unit costs")
  ap.add_argument("--existing-practices", default="", help="Optional: Path to existing practices.csv to avoid duplicates when expanding dataset")
  ap.add_argument("--limit-per-city", type=int, default=200)

  # Budget control flags
  ap.add_argument("--budget-usd", type=float, default=100.0, help="Total budget cap in USD (default 100)")
  ap.add_argument("--reserve-pct", type=float, default=10.0, help="Safety reserve percent (default 10%)")

  # Yelp/Google call caps
  ap.add_argument("--max-google-requests", type=int, default=1000, help="Hard cap on Google requests (default 1000)")
  ap.add_argument("--max-yelp-requests", type=int, default=4500, help="Hard cap on Yelp requests (optional)")

  # Google top-up target per city
  ap.add_argument("--google-fill-target-per-city", type=int, default=120,
                  help="If Yelp returns fewer than this for a city, use Google Text Search to top up (default 120)")

  args = ap.parse_args()

  cfg = load_config(args.config)
  gp_key = cfg.get("google_places_api_key","" )
  yelp_key = cfg.get("yelp_api_key","" )

  # Per-call unit costs (override here if pricing changes)
  gp_unit = float(cfg.get("google_places_unit_cost", 0.02))  # USD per Text Search request
  yelp_unit = float(cfg.get("yelp_unit_cost", 0.0))          # Yelp Fusion typically free

  # Compute budgeted call caps for Google
  reserve_multiplier = max(0.0, 1.0 - (args.reserve_pct/100.0))
  budget_for_calls = max(0.0, args.budget_usd) * reserve_multiplier
  google_cap_by_budget = 0 if not gp_key or gp_unit <= 0 else int(budget_for_calls // gp_unit)
  # Final Google cap considers both budget and explicit hard cap
  google_cap = min(google_cap_by_budget if google_cap_by_budget>0 else args.max_google_requests, args.max_google_requests)

  # Yelp cap (you can set one if you want to throttle even if $0)
  yelp_cap = args.max_yelp_requests if args.max_yelp_requests is not None else None

  print(f"[Budget] Total budget=${args.budget_usd:.2f}, reserve={args.reserve_pct:.1f}% -> usable=${budget_for_calls:.2f}")
  print(f"[Budget] Google per-call=${gp_unit:.4f}, derived cap={google_cap} calls (hard cap={args.max_google_requests})")
  print(f"[Budget] Yelp per-call=${yelp_unit:.4f}, cap={yelp_cap if yelp_cap is not None else 'unlimited'}")
  print(f"[Fill] Google top-up target per city: {args.google_fill_target_per_city} rows (Yelp-first)")

  rows = []
  gp_calls_used_total = 0
  yelp_calls_used_total = 0

  session = requests.Session()

  with open(args.seeds, "r", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
      city = r.get("city","" ).strip()
      if not city:
        continue

      # 1) Yelp first
      yelp_remaining = None if yelp_cap is None else max(0, yelp_cap - yelp_calls_used_total)
      if yelp_key and (yelp_cap is None or yelp_remaining > 0):
        got_yelp, used_yelp = yelp_city(session, yelp_key, city, args.limit_per_city, yelp_remaining)
        rows += got_yelp
        yelp_calls_used_total += used_yelp
        print(f"[Yelp]   {city}: used {used_yelp} calls (total {yelp_calls_used_total}/{yelp_cap if yelp_cap else '∞'}), rows={len(got_yelp)}")
        # YELP_NEAR_CAP_WARN
        if yelp_cap is not None and yelp_calls_used_total >= 4000:
          print("[Warning] Yelp requests >= 4000 — approaching the 4500 cap. Consider stopping soon to stay within the free tier.")
      else:
        print(f"[Yelp]   {city}: skipping (no key or cap reached)")
        got_yelp = []

      # 2) Google only if Yelp < target AND we have cap remaining
      need_topup = max(0, args.google_fill_target_per_city - len(got_yelp))
      if need_topup > 0 and gp_key and google_cap > gp_calls_used_total:
        gp_remaining_calls = max(0, google_cap - gp_calls_used_total)
        google_limit = min(args.limit_per_city, max(20, need_topup))
        got_gp, used_gp = google_places_city(session, gp_key, city, google_limit, gp_remaining_calls)
        rows += got_gp[:need_topup]
        gp_calls_used_total += used_gp
        print(f"[Google] {city}: used {used_gp} calls (total {gp_calls_used_total}/{google_cap}), rows={len(got_gp)} (added {min(len(got_gp), need_topup)} to hit target)")
      else:
        print(f"[Google] {city}: top-up not needed or cap reached")

      # Stop early if caps exhausted
      if (google_cap is not None and gp_calls_used_total >= google_cap) and \
         (not yelp_key or (yelp_cap is not None and yelp_calls_used_total >= yelp_cap)):
        print("[Budget] Caps reached; stopping further city lookups.")
        break

  # Load existing practices if provided (for expanding dataset without duplicates)
  seen = set()
  out_rows = []

  if args.existing_practices and Path(args.existing_practices).exists():
    print(f"[Dedup] Loading existing practices from {args.existing_practices}")
    with open(args.existing_practices, "r", encoding="utf-8-sig") as f:
      for existing_row in csv.DictReader(f):
        name = existing_row.get("name", "")
        address = existing_row.get("address", "")
        if name and address:
          key = (name.lower(), address.lower())
          seen.add(key)
          # Keep existing practices in output
          out_rows.append({
            "name": name,
            "website": existing_row.get("website", ""),
            "phone": existing_row.get("phone", ""),
            "address": address,
            "source": existing_row.get("source", "existing")
          })
    print(f"[Dedup] Loaded {len(out_rows)} existing practices; will skip duplicates")

  # Deduplicate new results by name+address
  initial_count = len(out_rows)
  for r in rows:
    key = (r["name"].lower(), r["address"].lower())
    if key in seen:
      continue
    seen.add(key)
    out_rows.append(r)

  new_count = len(out_rows) - initial_count
  print(f"[Dedup] Added {new_count} new unique practices (skipped {len(rows) - new_count} duplicates)")

  # Assign ids and basic columns
  Path(args.out).parent.mkdir(parents=True, exist_ok=True)
  with open(args.out, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["id","name","website","phone","address","source"])
    w.writeheader()
    for i, r in enumerate(out_rows, start=1):
      w.writerow({"id":i, **r})

  # Print a small budget summary
  google_spend = gp_calls_used_total * gp_unit if gp_key else 0.0
  yelp_spend = yelp_calls_used_total * yelp_unit if yelp_key else 0.0
  est_total = google_spend + yelp_spend
  print(f"[Budget] Estimated spend: Google=${google_spend:.2f} + Yelp=${yelp_spend:.2f} = ${est_total:.2f}")
  print("[Done] Wrote:", args.out)

if __name__ == "__main__":
  main()

#!/usr/bin/env python3
# Optional enrichment: query web search for job postings/snippets that mention PMS.
# Writes pms_clues_jobs and can upgrade likely_pms + pms_confidence.
import argparse, time, requests, pandas as pd, csv, os
from pathlib import Path

def load_config(path):
  import yaml
  with open(path, "r", encoding="utf-8") as f:
    return yaml.safe_load(f)

def search_bing(api_key, query, count=5, endpoint=None):
  # Use custom endpoint if provided, otherwise use default
  url = endpoint or "https://api.bing.microsoft.com/v7.0/search"
  headers = {"Ocp-Apim-Subscription-Key": api_key}
  params = {"q": query, "count": count, "mkt": "en-US", "responseFilter":"Webpages"}
  r = requests.get(url, headers=headers, params=params, timeout=20)
  if r.status_code != 200:
    return []
  js = r.json()
  items = []
  for w in js.get("webPages", {}).get("value", []):
    items.append({"name": w.get("name",""), "url": w.get("url",""), "snippet": w.get("snippet","")})
  return items

def search_serpapi(api_key, query, count=5):
  url = "https://serpapi.com/search.json"
  params = {"engine":"google", "q":query, "num":count, "api_key":api_key}
  r = requests.get(url, params=params, timeout=20)
  if r.status_code != 200:
    return []
  js = r.json()
  items = []
  for w in js.get("organic_results", []):
    items.append({"name": w.get("title",""), "url": w.get("link",""), "snippet": w.get("snippet","")})
  return items

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--in", dest="input_file", required=True, help="results.csv from crawler")
  ap.add_argument("--out", required=True, help="output enriched CSV")
  ap.add_argument("--config", required=True, help="config.yaml with API keys")
  args = ap.parse_args()

  cfg = load_config(args.config)
  bing_key = cfg.get("bing_search_api_key","")
  bing_endpoint = cfg.get("bing_search_endpoint","")
  serp_key = cfg.get("serpapi_api_key","")

  if not bing_key and not serp_key:
    print("[Error] No search API keys found in config. Need bing_search_api_key or serpapi_api_key.")
    return

  # Load input CSV
  df = pd.read_csv(args.input_file)

  # Check for already processed practices (resume support)
  processed_ids = set()
  file_exists = Path(args.out).exists()
  write_mode = 'a' if file_exists else 'w'

  if file_exists:
    print(f"[Resume] Output file exists, loading already-processed practices...")
    existing_df = pd.read_csv(args.out)
    processed_ids = set(existing_df['id'].values) if 'id' in existing_df.columns else set()
    print(f"[Resume] Found {len(processed_ids)} already-processed practices, will skip them")

  # Get all column names from input, plus our new column
  input_columns = df.columns.tolist()
  if 'pms_clues_jobs' not in input_columns:
    input_columns.append('pms_clues_jobs')

  # Open output file for incremental writing
  csv_file = None
  csv_writer = None
  total_processed = 0
  newly_processed = 0

  try:
    csv_file = open(args.out, write_mode, newline='', encoding='utf-8')
    csv_writer = csv.DictWriter(csv_file, fieldnames=input_columns)

    # Write header if new file
    if not file_exists:
      csv_writer.writeheader()
      csv_file.flush()

    print(f"[Start] Processing {len(df)} practices from {args.input_file}")

    for idx, row in df.iterrows():
      practice_id = row.get('id', idx)

      # Skip if already processed
      if practice_id in processed_ids:
        total_processed += 1
        continue

      # Get practice name
      name = str(row.get("name",""))[:80]
      if not name:
        # Write row as-is with empty pms_clues_jobs
        row_dict = row.to_dict()
        row_dict['pms_clues_jobs'] = ""
        csv_writer.writerow(row_dict)
        csv_file.flush()
        total_processed += 1
        newly_processed += 1
        continue

      # Search for job postings
      q = f'"{name}" ("Open Dental" OR Dentrix OR Eaglesoft OR "Curve Dental" OR Denticon OR "Practice-Web" OR Dolphin)'
      items = []
      try:
        if bing_key:
          items += search_bing(bing_key, q, count=5, endpoint=bing_endpoint if bing_endpoint else None)
        if serp_key and not items:
          items += search_serpapi(serp_key, q, count=5)
      except Exception as e:
        print(f"[Error] Search failed for '{name}': {e}")

      # Extract PMS clues from job postings
      hits = []
      for it in items:
        snip = (it.get("snippet","") or "").lower()
        url = it.get("url","")
        if "open dental" in snip:
          hits.append(f"open_dental:JOBS:{url}")
        if "dentrix" in snip:
          hits.append(f"dentrix:JOBS:{url}")
        if "eaglesoft" in snip:
          hits.append(f"eaglesoft:JOBS:{url}")
        if "curve dental" in snip or "curvehero" in snip:
          hits.append(f"curve_dental:JOBS:{url}")
        if "denticon" in snip:
          hits.append(f"denticon:JOBS:{url}")
        if "practice-web" in snip or "practiceweb" in snip:
          hits.append(f"practice_web:JOBS:{url}")
        if "dolphin" in snip:
          hits.append(f"dolphin:JOBS:{url}")

      pms_clues_jobs = ";".join(hits[:5])

      # Strengthen likely_pms if job evidence is decisive
      likely_pms = row.get("likely_pms", "unknown")
      pms_confidence = float(row.get("pms_confidence", 0))

      if pms_clues_jobs:
        pmss = set([p.split(":")[0] for p in pms_clues_jobs.split(";") if p])
        if len(pmss) == 1:
          # Only one PMS in job postings - high confidence
          only_pms = list(pmss)[0]
          likely_pms = only_pms
          pms_confidence = max(pms_confidence, 0.8)

      # Write enriched row immediately
      row_dict = row.to_dict()
      row_dict['pms_clues_jobs'] = pms_clues_jobs
      row_dict['likely_pms'] = likely_pms
      row_dict['pms_confidence'] = pms_confidence

      csv_writer.writerow(row_dict)
      csv_file.flush()

      total_processed += 1
      newly_processed += 1

      # Progress update every 50 practices
      if newly_processed % 50 == 0:
        pct = (total_processed / len(df)) * 100
        print(f"[Progress] {total_processed}/{len(df)} practices ({pct:.1f}%) - {newly_processed} newly enriched", flush=True)

      # Rate limiting
      time.sleep(0.4)

    print(f"[Done] Processed {total_processed}/{len(df)} practices ({newly_processed} newly enriched)")
    print(f"[Done] Output written to: {args.out}")

  finally:
    if csv_file:
      csv_file.close()

if __name__ == "__main__":
  main()

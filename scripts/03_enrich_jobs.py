#!/usr/bin/env python3
# Optional enrichment: query web search for job postings/snippets that mention PMS.
# Writes pms_clues_jobs and can upgrade likely_pms + pms_confidence.
import argparse, time, requests, pandas as pd

def load_config(path):
  import yaml
  with open(path, "r", encoding="utf-8") as f:
    return yaml.safe_load(f)

def search_bing(api_key, query, count=5):
  url = "https://api.bing.microsoft.com/v7.0/search"
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
  ap.add_argument("--in", required=True, help="results.csv from crawler")
  ap.add_argument("--out", required=True, help="output enriched CSV")
  ap.add_argument("--config", required=True, help="config.yaml with API keys")
  args = ap.parse_args()

  cfg = load_config(args.config)
  bing_key = cfg.get("bing_search_api_key","")
  serp_key = cfg.get("serpapi_api_key","")

  df = pd.read_csv(args.in)
  df["pms_clues_jobs"] = ""

  for idx, row in df.iterrows():
    name = str(row.get("name",""))[:80]
    if not name:
      continue
    q = f'"{name}" ("Open Dental" OR Dentrix OR Eaglesoft)'
    items = []
    if bing_key:
      items += search_bing(bing_key, q, count=5)
    if serp_key and not items:
      items += search_serpapi(serp_key, q, count=5)
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
    df.at[idx, "pms_clues_jobs"] = ";".join(hits[:5])
    time.sleep(0.4)

  # Upgrade likely_pms if job evidence is decisive
  def strengthen(row):
    jp = str(row.get("pms_clues_jobs",""))
    guess = row.get("likely_pms","unknown")
    conf = float(row.get("pms_confidence", 0))
    # If only one PMS appears in job clues, bump confidence & set guess
    pmss = set([p.split(":")[0] for p in jp.split(";") if p])
    if len(pmss) == 1:
      only = list(pmss)[0]
      return only, max(conf, 0.8)
    return guess, conf

  new_guess, new_conf = [], []
  for _, r in df.iterrows():
    g, c = strengthen(r)
    new_guess.append(g); new_conf.append(c)
  df["likely_pms"] = new_guess
  df["pms_confidence"] = new_conf

  df.to_csv(args.out, index=False)

if __name__ == "__main__":
  main()

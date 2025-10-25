# Flex Practice Audit — End-to-End Toolkit

This toolkit builds a **large sample of dental practices**, **crawls their websites**, detects **online booking & payments**, infers **PMS fingerprints (Open Dental, Dentrix, Eaglesoft)**, identifies **third-party platforms** (Weave, Dental Intel, etc.), detects **phone providers**, and produces **summary stats**.

## Pipeline Overview

1. **Build a practice list** (thousands): `scripts/01_build_practice_list.py`
   - Inputs: `sample/seeds.sample.csv` (cities) or your own list
   - Sources: Google Places API, Yelp Fusion API (bring your API keys)
   - Output: `data/practices.csv` with `id,name,website,phone,address`

2. **Crawl & Detect**: `scripts/02_crawl_detect.py`
   - Async crawl of homepage + key subpages (`/appointment`, `/forms`, `/pay`, `/portal`, `/contact`)
   - Optional JS render fallback with **Playwright** (set `--use-js` to enable)
   - Uses regex **patterns** in `patterns/*.yaml`
   - Output:
     - `data/detections.jsonl` (one JSON per site with detailed evidence)
     - `data/results.csv` (flattened features + probabilities)

3. **Enrich with job posts (optional, boosts PMS confidence)**: `scripts/03_enrich_jobs.py`
   - Uses **Bing Web Search API** or **SerpAPI** to look up `"{practice name}" + ("Open Dental"|"Dentrix"|"Eaglesoft")`
   - Output: `data/job_enrichment.csv` + merged `data/results.enriched.csv`

3. **Summary Stats**: `scripts/04_summary_stats.py`
   - Reads `data/results*.csv`
   - Outputs `data/summary.csv` and `data/summary.json`
   - Prints a readable table of the key metrics

## Quickstart

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -U pip wheel
pip install -r requirements.txt

# 1) Build practice list (requires API keys)
cp config.example.yaml config.yaml
# Edit config.yaml with your API keys
python scripts/01_build_practice_list.py --seeds sample/seeds.sample.csv --out data/practices.csv --config config.yaml --limit-per-city 200

# 2) Crawl & detect (works without Playwright; to enable JS rendering, install and pass --use-js)
python scripts/02_crawl_detect.py --in data/practices.csv --out-csv data/results.csv --out-jsonl data/detections.jsonl --concurrency 20

# 3) (Optional) Job post enrichment
python scripts/03_enrich_jobs.py --in data/results.csv --out data/results.enriched.csv --config config.yaml

# 4) Summary stats
python scripts/04_summary_stats.py --in data/results.enriched.csv --out-json data/summary.json --out-csv data/summary.csv
```

> Tip: Run the crawler in **batches** (e.g., per state) and monitor HTTP errors. Respect robots.txt and rate-limit politely.

## Outputs

- **Per-practice fields (results.csv)**:
  - `website`, `final_url`, `http_status`
  - `has_online_booking`, `has_online_payments`, `has_online_forms`
  - `pms_guess`, `pms_confidence`, `pms_evidence` (semicolon-separated)
  - `third_party_booking`, `third_party_forms`, `third_party_payments`, `third_party_all` (semicolon-separated lists)
  - `phone_providers` (semicolon-separated)
  - `evidence_urls` (semicolon-separated of the strongest signals)

- **Summary stats**:
  - `% with online booking`, `% with online payments`, `% with online forms`
  - `% by PMS provider (Open Dental, Dentrix, Eaglesoft, Unknown)`
  - `% using third-party solution for booking/forms/payments`
  - `% by phone provider (Weave, RingCentral, Nextiva, Dialpad, Vonage, 8x8, Mango, etc.)`

## Configuration

Copy `config.example.yaml` → `config.yaml` and fill:
```yaml
google_places_api_key: "YOUR_GOOGLE_PLACES_KEY"
yelp_api_key: "YOUR_YELP_FUSION_KEY"
bing_search_api_key: "YOUR_BING_SEARCH_KEY"   # optional (for job posts)
serpapi_api_key: "YOUR_SERPAPI_KEY"           # optional (for job posts)
```

## Legal & Ethical
- Use only public web data. Comply with site terms and **robots.txt**. Add delays and backoff. Avoid scraping pages that prohibit it.
- For any outreach, be transparent about how you inferred tech stack.


## Updates for Atlanta test & deeper detection

- **Atlanta-first test:** `sample/seeds.sample.csv` now starts with Atlanta, GA. Add more cities by adding rows.
- **JS-rendered widgets:** `scripts/02_crawl_detect.py` supports `--use-js` to render pages with Playwright and detect widgets that load after JS.
- **Evidence breakout:** Output splits clues by category:
  - `pms_clues_site` (from website), `pms_clues_jobs` (from enrichment), and `likely_pms`
  - `third_party_booking_clues`, `third_party_forms_clues`, `third_party_payments_clues`, plus `likely_booking_vendor`
  - `phone_clues_site`, plus `likely_phone_provider`


### Budget & Caps
- Yelp calls default-capped at **4500**; warning at **4000**; when cap is reached, the script writes `yelp_cap_reached.txt` next to your output and **stops using Yelp**.
- Google calls are capped by `--max-google-requests` and/or budget; when the cap is reached, the script writes `google_cap_reached.txt` and **stops using Google**.

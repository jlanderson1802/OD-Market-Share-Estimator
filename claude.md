# OD Market Share Estimator

## Project Overview

This project estimates market share for dental practice management software (PMS) and related technology vendors (online booking, payments, forms, phone systems) by crawling dental practice websites and analyzing their technology stack.

**Primary Goal:** Determine the market penetration of Open Dental and competing PMS systems across dental practices in the United States.

## Architecture

The project follows a multi-stage data pipeline:

```
1. Practice Discovery (Google Places API)
   ↓
2. Website Crawling (aiohttp + pattern matching)
   ↓
3. Optional: Job Posting Enrichment (Bing Search API)
   ↓
4. Statistical Analysis & Reporting
```

## Key Components

### 1. Practice List Builder (`scripts/01_build_practice_list.py`)

**Purpose:** Build a dataset of dental practices from Google Places API

**Key Features:**
- Searches for "dentist" in cities from a seed CSV
- Fetches practice details (name, address, phone, website)
- Budget control with configurable caps (default: $100 USD)
- Deduplication support via `--existing-practices` flag
- Cost estimation and progress tracking

**Usage:**
```bash
python scripts/01_build_practice_list.py \
  --seeds sample/seeds_fullscale.csv \
  --out data/practices.csv \
  --config config.yaml \
  --limit-per-city 200 \
  --budget-usd 100
```

**Important Parameters:**
- `--existing-practices`: Path to existing CSV to avoid duplicates when expanding dataset
- `--google-fill-target-per-city`: Number of practices to fetch per city (default: 120)
- `--max-google-requests`: Hard cap on API calls (default: 1000)

**Deduplication:** Uses `(name.lower(), address.lower())` as unique key

### 2. Website Crawler (`scripts/02_crawl_detect.py`)

**Purpose:** Crawl practice websites to detect technology stack

**Key Features:**
- Async crawling with aiohttp (configurable concurrency)
- Robots.txt compliance with politeness delays
- Pattern matching for PMS, booking, payment, forms, and phone vendors
- **Incremental writing** - writes results immediately to disk
- Progress reporting every 50 sites
- Crash resilience with try/finally blocks

**Usage:**
```bash
python scripts/02_crawl_detect.py \
  --in data/practices.csv \
  --out-csv data/results.csv \
  --out-jsonl data/detections.jsonl \
  --concurrency 20
```

**Detection Categories:**
- **PMS (Practice Management Software):** Open Dental, Dentrix, Eaglesoft, Curve Dental, Denticon, Practice-Web, Dolphin
- **Booking:** NexHealth, Zocdoc, LocalMed, Weave, etc.
- **Payments:** Square, CareCredit, Stripe, Rectangle Health
- **Forms:** JotForm, IntakeQ, Typeform, Gravity Forms
- **Phone:** RingCentral, Weave, Yapi, CallRail

**Incremental Writing:** Results are written row-by-row with immediate flush() for crash resilience

### 3. Job Posting Enrichment (`scripts/03_enrich_jobs.py`)

**Purpose:** Enrich PMS detection by searching job postings that mention practice name + PMS systems

**Key Features:**
- Searches Bing (or SerpAPI) for job postings mentioning practice + PMS
- Adds `pms_clues_jobs` column with detected PMS systems
- Upgrades `likely_pms` and `pms_confidence` if evidence is decisive
- **Incremental writing** with resume support
- Progress reporting every 50 practices
- Rate limiting (0.4s delay between requests)

**Usage:**
```bash
python scripts/03_enrich_jobs.py \
  --in data/results.csv \
  --out data/results_with_jobs.csv \
  --config config.yaml
```

**Resume Support:** Can restart from interruption by skipping already-processed practices

**API Support:**
- Bing Search API (primary)
- SerpAPI (fallback)
- Custom Azure endpoints via `bing_search_endpoint` in config

### 4. Summary Statistics (`scripts/04_summary_stats.py`)

**Purpose:** Generate statistical summaries from crawl results

**Outputs:**
- Overall technology adoption rates
- Vendor-specific breakdowns
- PMS market share estimates
- Success/failure rates

### 5. Vendor Analysis (`scripts/analyze_vendors.py`)

**Purpose:** Detailed vendor distribution analysis

**Outputs:**
- Booking vendor frequency and market share
- Payment vendor frequency and market share
- Forms vendor frequency and market share
- URL extraction and vendor identification from external links

## Data Flow

### Input Files

**`sample/seeds_fullscale.csv`** - List of cities to search
```csv
city
New York, NY
Los Angeles, CA
...
```

**`config.yaml`** - API keys and configuration (not in git)
```yaml
google_places_api_key: "YOUR_KEY"
bing_search_api_key: "YOUR_KEY"
bing_search_endpoint: "https://YOUR_RESOURCE.cognitiveservices.azure.com/bing/v7.0/search"  # Optional
serpapi_api_key: "YOUR_KEY"  # Optional

# Unit costs for budgeting
google_places_unit_cost: 0.02
yelp_unit_cost: 0.0
```

### Output Files

**`data/practices.csv`** - Practice list from Google Places
```csv
id,name,website,phone,address,source
1,Sample Dental,https://example.com,(555) 123-4567,"123 Main St, City, ST",google_places
```

**`data/results.csv`** - Website crawl results
```csv
id,name,website,final_url,http_status,has_online_booking,has_online_forms,has_online_payments,
third_party_booking_clues,third_party_forms_clues,third_party_payments_clues,
likely_booking_vendor,phone_clues_site,likely_phone_provider,
pms_clues_site,likely_pms,pms_confidence,evidence_urls,
booking_urls,payment_urls,forms_urls
```

**`data/detections.jsonl`** - Raw detection data (JSONL format)

**`data/results_with_jobs.csv`** - Enriched with job posting data

## Pattern Matching

### Detection Patterns Location

All detection patterns are in `patterns/*.yaml`:

- **`pms_patterns.yaml`** - Practice Management Software patterns
- **`third_party_patterns.yaml`** - Booking, payment, forms vendors
- **`phone_patterns.yaml`** - Phone system providers

### Pattern Structure

```yaml
strong:
  vendor_name:
    - r"regex_pattern_1"
    - r"regex_pattern_2"

medium:
  vendor_name:
    - r"less_specific_pattern"

weak:
  vendor_name:
    - r"very_generic_pattern"
```

**Pattern Priority:** strong > medium > weak

**Confidence Calculation:** Based on pattern strength and number of matches

## Common Workflows

### 1. Initial Dataset Creation

```bash
# Build initial practice list (3K practices, ~$60)
python scripts/01_build_practice_list.py \
  --seeds sample/seeds_fullscale.csv \
  --out data/practices.csv \
  --config config.yaml \
  --limit-per-city 30 \
  --budget-usd 100

# Crawl practice websites
python scripts/02_crawl_detect.py \
  --in data/practices.csv \
  --out-csv data/results.csv \
  --out-jsonl data/detections.jsonl \
  --concurrency 20

# Generate summary statistics
python scripts/04_summary_stats.py data/results.csv
```

### 2. Expanding Existing Dataset

```bash
# Expand from 3K to 6K practices with deduplication
python scripts/01_build_practice_list.py \
  --seeds sample/seeds_fullscale.csv \
  --out data/practices_10k.csv \
  --config config.yaml \
  --existing-practices data/practices.csv \
  --limit-per-city 99 \
  --budget-usd 300

# Crawl new larger dataset
python scripts/02_crawl_detect.py \
  --in data/practices_10k.csv \
  --out-csv data/results_6k.csv \
  --out-jsonl data/detections_6k.jsonl \
  --concurrency 20
```

### 3. Job Posting Enrichment

```bash
# Enrich with job posting data
python scripts/03_enrich_jobs.py \
  --in data/results.csv \
  --out data/results_with_jobs.csv \
  --config config.yaml
```

### 4. Vendor Analysis

```bash
# Analyze vendor distributions
python scripts/analyze_vendors.py
```

## Important Implementation Details

### Incremental Writing

Both the website crawler and job enrichment scripts use incremental writing:

1. **Open output files at start** (not end)
2. **Write each result immediately** with `flush()`
3. **Use try/finally** to ensure proper file closure
4. **Thread-safe** with locks (crawler only, as it's async)

**Benefits:**
- Crash resilience - partial results saved
- Lower memory usage - no accumulation
- Real-time progress monitoring with `tail -f`

### Resume Support

The job enrichment script can resume from interruption:

1. Checks if output file exists
2. Loads already-processed practice IDs
3. Skips those practices in new run
4. Appends only new results

### Deduplication Strategy

Practice deduplication uses `(name.lower(), address.lower())` as unique key:

- **Expected duplicate rate:** ~40-50% when expanding dataset
- **Reason:** Dental chains and DSOs appear in multiple cities
- **Examples:** Aspen Dental, Bright Now Dental, etc.

### API Cost Management

Google Places API costs ~$0.02 per Text Search request:

- **3,000 practices:** ~$60 (3,150 API calls)
- **6,000 practices:** ~$126 (6,300 API calls)
- **10,000 practices:** ~$200 (10,000 API calls)

Budget control via `--budget-usd` and `--max-google-requests` flags.

### Crawler Performance

Website crawler performance metrics:

- **Concurrency:** 20 concurrent requests (configurable)
- **Success rate:** ~85-90% typically
- **Speed:** ~150-200 practices per minute
- **Politeness delay:** 1 second between requests to same host
- **Robots.txt compliance:** Enabled by default

## Analysis Insights (as of current data)

### Technology Adoption Rates

- **Online Booking:** 26.8% of practices
- **Online Payments:** 32.4% of practices
- **Online Forms:** 11.4% of practices (major opportunity gap)

### Vendor Market Share

**Booking Systems:**
- NexHealth: 14.6%
- Weave: 11.5%
- LocalMed: 4.5%

**Payment Systems:**
- Square: 91.5% (dominant)
- CareCredit: 3.0%
- Stripe: 2.4%

**Forms Systems:**
- IntakeQ: 45.7%
- JotForm: 29.0%

**Key Finding:** All detected features are third-party services (no self-hosted solutions detected)

## Development Notes

### Adding New Vendors

1. Add detection patterns to appropriate YAML file in `patterns/`
2. Update vendor mapping in `scripts/analyze_vendors.py`
3. Test patterns against sample websites
4. Document expected URL patterns

### Improving Detection Accuracy

1. Review `data/detections.jsonl` for false positives/negatives
2. Add stronger patterns to `patterns/*.yaml`
3. Consider additional evidence sources (job postings, social media)
4. Cross-reference multiple detection methods

### Handling Rate Limits

If hitting API rate limits:

1. Reduce `--concurrency` for website crawler
2. Increase `time.sleep()` delay in job enrichment
3. Use `--max-google-requests` to cap budget
4. Consider running in multiple smaller batches

## Git Workflow

**What's in Git:**
- All Python scripts
- Pattern YAML files
- Documentation (README, claude.md)
- Example config (`config.example.yaml`)

**What's NOT in Git (in .gitignore):**
- `config.yaml` (contains API keys)
- `data/*.csv` (large data files)
- `data/*.jsonl` (large data files)
- `venv/` (Python virtual environment)

## Future Enhancements

Potential improvements documented in project files:

1. **Crawler improvements** (see `crawler-updates.md`)
   - ✅ Incremental writing (IMPLEMENTED)
   - ⏳ Retry logic for failed requests
   - ⏳ User agent rotation
   - ⏳ Proxy support

2. **Detection improvements**
   - Add more PMS systems (Practice Works, Dentally, etc.)
   - Machine learning for pattern matching
   - Screenshot analysis for visual elements
   - Social media signal integration

3. **Analysis improvements**
   - Geographic distribution analysis
   - Practice size correlation
   - Technology stack clustering
   - Trend analysis over time

## Contact

For questions or issues, contact the repository owner or open an issue on GitHub.

## Related Documentation

- `README.md` - Project overview and quick start
- `vendor-analysis.md` - Detailed vendor analysis results
- `crawler-updates.md` - Incremental writing implementation notes
- `config.example.yaml` - Example configuration file

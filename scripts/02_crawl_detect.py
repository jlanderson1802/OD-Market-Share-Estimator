#!/usr/bin/env python3
import asyncio, aiohttp, re, csv, json, argparse, sys, time, random, threading
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from collections import defaultdict
import urllib.robotparser as robotparser

# ================= Politeness Defaults =================
DEFAULT_TIMEOUT = 20  # per request timeout (seconds)
GLOBAL_CONCURRENCY_DEFAULT = 10
PER_HOST_CONCURRENCY = 1
PER_HOST_DELAY_BASE = 1.0  # seconds
PER_HOST_DELAY_JITTER = 1.0  # seconds
PER_HOST_MAX_PAGES = 5  # we'll cap requests per host per run
MAX_CONSECUTIVE_ERRORS_PER_HOST = 3

BACKOFF_INITIAL = 2.0
BACKOFF_CAP = 60.0

FAIL_ALERT_PCT_DEFAULT = 15.0  # alert if failure % exceeds this

USER_AGENT = "FlexAuditBot/1.0 (+https://example.com/contact; mailto:ops@example.com)"

# =======================================================

def load_yaml(p):
  import yaml
  with open(p, "r", encoding="utf-8") as f:
    return yaml.safe_load(f)

def norm_url(u):
  if not u: return None
  u = u.strip()
  if not u: return None
  if not u.startswith("http"):
    u = "http://" + u
  return u.rstrip("/")

def make_targets(base):
  paths = ["", "/appointment", "/appointments", "/book", "/schedule", "/forms", "/new-patient-forms",
           "/pay", "/payment", "/patient-portal", "/portal", "/contact"]
  return [urljoin(base, p) for p in paths]

def is_captcha(html: str) -> bool:
  if not html: return False
  hay = html.lower()
  return any(k in hay for k in [
    "captcha", "are you human", "unusual traffic", "cloudflare", "verify you are a human"
  ])

class HostState:
  __slots__ = (
    "sem", "last_request_ts", "consec_errors", "backoff", "robots", "pages_count", "crawl_delay",
    # robots.txt caching
    "robots_fetch_time", "robots_cache_duration",
    # metrics
    "pages_attempted", "pages_fetched", "http_2xx", "http_403", "http_429", "http_5xx", "other_4xx",
    "captcha_hits", "disallowed_paths", "backoff_events", "evidence_urls_sample"
  )
  def __init__(self):
    self.sem = asyncio.Semaphore(PER_HOST_CONCURRENCY)
    self.last_request_ts = 0.0
    self.consec_errors = 0
    self.backoff = 0.0
    self.robots = None
    self.pages_count = 0
    self.crawl_delay = None
    # robots.txt caching
    self.robots_fetch_time = 0.0
    self.robots_cache_duration = 3600.0  # Cache for 1 hour
    # metrics
    self.pages_attempted = 0
    self.pages_fetched = 0
    self.http_2xx = 0
    self.http_403 = 0
    self.http_429 = 0
    self.http_5xx = 0
    self.other_4xx = 0
    self.captcha_hits = 0
    self.disallowed_paths = 0
    self.backoff_events = 0
    self.evidence_urls_sample = []

async def fetch_robots(session, base_url, host_state: HostState):
  # Check if we have a cached robots.txt that's still valid
  current_time = time.time()
  if host_state.robots_fetch_time > 0:
    if current_time - host_state.robots_fetch_time < host_state.robots_cache_duration:
      return  # Use cached robots.txt
  
  try:
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    
    # Add retry logic for robots.txt failures
    for attempt in range(3):
      try:
        async with asyncio.timeout(DEFAULT_TIMEOUT):
          async with session.get(robots_url, headers={"User-Agent": USER_AGENT}, ssl=False) as resp:
            if resp.status == 200:
              text = await resp.text(errors="ignore")
              rp = robotparser.RobotFileParser()
              lines = text.splitlines()
              rp.parse(lines)
              # crawl-delay isn't always exposed by robotparser; parse manually
              cd = None
              for line in lines:
                if "crawl-delay" in line.lower():
                  m = re.search(r"crawl-delay\s*:\s*([0-9\.]+)", line, re.I)
                  if m:
                    try:
                      cd = float(m.group(1))
                    except:
                      cd = None
              host_state.crawl_delay = cd
              host_state.robots = rp
              host_state.robots_fetch_time = current_time
              return
            elif resp.status == 404:
              # No robots.txt = allow all
              rp = robotparser.RobotFileParser()
              rp.set_url(robots_url)
              rp.read()  # empty => allow by default
              host_state.robots = rp
              host_state.robots_fetch_time = current_time
              return
            elif resp.status == 403:
              # robots.txt forbidden = disallow all
              rp = robotparser.RobotFileParser()
              rp.set_url(robots_url)
              rp.read()
              host_state.robots = rp
              host_state.robots_fetch_time = current_time
              return
            else:
              # Other status codes - retry
              if attempt < 2:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
              else:
                # Last attempt failed - default to permissive
                rp = robotparser.RobotFileParser()
                rp.set_url(robots_url)
                rp.read()
                host_state.robots = rp
                host_state.robots_fetch_time = current_time
                return
      except Exception as e:
        if attempt < 2:
          await asyncio.sleep(2 ** attempt)  # Exponential backoff
          continue
        else:
          # Last attempt failed - fallback to permissive
          rp = robotparser.RobotFileParser()
          rp.set_url(base_url + "/robots.txt")
          try:
            rp.read()
          except:
            pass  # If sync read also fails, use empty robots
          host_state.robots = rp
          host_state.robots_fetch_time = current_time
          return
  except Exception:
    # Fallback to permissive
    rp = robotparser.RobotFileParser()
    rp.set_url(base_url + "/robots.txt")
    try:
      rp.read()
    except:
      pass  # If sync read also fails, use empty robots
    host_state.robots = rp
    host_state.robots_fetch_time = current_time

async def polite_wait(host_state: HostState):
  # per-host delay with jitter and backoff
  now = time.time()
  delay = PER_HOST_DELAY_BASE + random.uniform(0, PER_HOST_DELAY_JITTER)
  if host_state.crawl_delay is not None:
    delay = max(delay, host_state.crawl_delay)
  if host_state.backoff > 0:
    delay = max(delay, host_state.backoff)
  elapsed = now - host_state.last_request_ts
  wait_for = max(0.0, delay - elapsed)
  if wait_for > 0:
    await asyncio.sleep(wait_for)

async def fetch_http(session, url, host_state: HostState):
  headers = {"User-Agent": USER_AGENT}
  await polite_wait(host_state)
  host_state.pages_attempted += 1
  try:
    async with asyncio.timeout(DEFAULT_TIMEOUT):
      async with host_state.sem:
        async with session.get(url, headers=headers, ssl=False, allow_redirects=True) as resp:
          text = await resp.text(errors="ignore")
          host_state.last_request_ts = time.time()
          status = resp.status
          if status == 429 or status == 503:
            host_state.http_5xx += (1 if status == 503 else 0)
            if status == 429: host_state.http_429 += 1
            host_state.backoff = min(BACKOFF_CAP, host_state.backoff * 2 if host_state.backoff else BACKOFF_INITIAL)
            host_state.backoff_events += 1
          elif status == 403:
            host_state.http_403 += 1
          elif 200 <= status < 300:
            host_state.http_2xx += 1
            host_state.pages_fetched += 1
            # reset backoff on success
            host_state.backoff = 0.0
          elif 400 <= status < 500:
            host_state.other_4xx += 1
          return status, str(resp.url), resp.headers.get("content-type",""), text
  except Exception:
    host_state.last_request_ts = time.time()
    return None, url, "", ""

async def fetch_js(playwright_ctx, url, host_state: HostState):
  await polite_wait(host_state)
  host_state.pages_attempted += 1
  page = await playwright_ctx["browser"].new_page(user_agent=USER_AGENT)
  page.set_default_timeout(playwright_ctx["timeout"])
  try:
    await page.goto(url, wait_until="domcontentloaded")
    try:
      await page.wait_for_load_state("networkidle", timeout=playwright_ctx["timeout"])
    except:
      pass
    html = await page.content()
    final_url = page.url
    await page.close()
    host_state.last_request_ts = time.time()
    host_state.http_2xx += 1
    host_state.pages_fetched += 1
    host_state.backoff = 0.0
    return 200, final_url, "text/html", html
  except Exception:
    try:
      await page.close()
    except Exception:
      pass
    host_state.last_request_ts = time.time()
    return None, url, "", ""

def find_matches(patterns, blob):
  hits = []
  for pat in patterns:
    match = re.search(pat, blob, flags=re.IGNORECASE)
    if match:
      # Extract the actual matched text instead of the pattern
      matched_text = match.group(0)
      hits.append(matched_text)
  return list(set(hits))

def extract_links(soup):
  L = []
  for a in soup.find_all("a", href=True):
    href = a["href"].strip()
    if href.startswith("mailto:"):
      continue
    L.append(href)
  return L

def extract_external_service_urls(links, practice_domain):
  """Extract external URLs that might be booking/payment/forms services"""
  booking_urls = []
  payment_urls = []
  forms_urls = []

  # Patterns that indicate booking/payment/forms in URLs
  booking_patterns = [
    r'book', r'appointment', r'schedule', r'calendar',
    r'nexhealth', r'localmed', r'zocdoc', r'weave', r'solutionreach',
    r'recallmax', r'dental4\.me', r'curvehero', r'yapi'
  ]
  payment_patterns = [r'pay', r'payment', r'billing', r'stripe', r'square']
  forms_patterns = [r'form', r'intake', r'jotform', r'typeform', r'docusign']

  for link in links:
    if not link.startswith('http'):
      continue

    try:
      parsed = urlparse(link)
      link_domain = parsed.netloc.lower()

      # Skip if it's the practice's own domain
      if practice_domain and practice_domain.lower() in link_domain:
        continue

      link_lower = link.lower()

      # Check for booking URLs
      if any(re.search(pat, link_lower) for pat in booking_patterns):
        booking_urls.append(link)

      # Check for payment URLs
      if any(re.search(pat, link_lower) for pat in payment_patterns):
        payment_urls.append(link)

      # Check for forms URLs
      if any(re.search(pat, link_lower) for pat in forms_patterns):
        forms_urls.append(link)

    except:
      continue

  return list(set(booking_urls)), list(set(payment_urls)), list(set(forms_urls))

def score_pms(pms_patterns, site_combined, job_links_text=""):
  evidence_site = []
  evidence_jobs = []
  score = {"open_dental":0, "dentrix":0, "eaglesoft":0}
  strong = pms_patterns.get("strong",{})
  weak = pms_patterns.get("weak",{})

  for vendor in score.keys():
    s_hits = find_matches(strong.get(vendor, []), site_combined)
    w_hits = find_matches(weak.get(vendor, []), site_combined)
    if s_hits:
      score[vendor] += 5 * len(s_hits)
      evidence_site += [f"{vendor}:STRONG:{h}"] * len(s_hits)
    if w_hits:
      score[vendor] += 1 * len(w_hits)
      evidence_site += [f"{vendor}:WEAK:{h}"] * len(w_hits)

  if job_links_text:
    for vendor in score.keys():
      if vendor == "open_dental":
        if re.search(r"\bopen dental\b", job_links_text, re.I):
          evidence_jobs.append("open_dental:JOBS:mention")
      elif vendor == "dentrix":
        if re.search(r"\bdentrix\b", job_links_text, re.I):
          evidence_jobs.append("dentrix:JOBS:mention")
      elif vendor == "eaglesoft":
        if re.search(r"\beaglesoft\b", job_links_text, re.I):
          evidence_jobs.append("eaglesoft:JOBS:mention")

  guess = max(score, key=lambda k: score[k])
  total = sum(score.values())
  conf = (score[guess] / total) if total else 0.0
  return (guess if score[guess] > 0 else "unknown", round(conf,3), evidence_site, evidence_jobs)

async def audit_site(session, row, pms_patterns, third_patterns, phone_patterns, use_js, playwright_ctx, host_states):
  rid = row.get("id","")
  name = row.get("name","")
  website = norm_url(row.get("website",""))
  if not website:
    return None

  parsed = urlparse(website)
  host = parsed.netloc
  host_state = host_states[host]

  # robots.txt
  if host_state.robots is None:
    await fetch_robots(session, website, host_state)

  # Check robots for each target path
  targets = make_targets(website)
  allowed_targets = []
  for u in targets:
    if host_state.pages_count >= PER_HOST_MAX_PAGES:
      break
    if host_state.robots:
      if not host_state.robots.can_fetch(USER_AGENT, u):
        host_state.disallowed_paths += 1
        continue
    allowed_targets.append(u)

  evidence_urls = []
  site_html, site_links, site_texts = [], [], []
  all_links = []  # Collect all links for external service URL extraction
  final_url = ""
  http_status = ""

  for u in allowed_targets:
    if host_state.consec_errors >= MAX_CONSECUTIVE_ERRORS_PER_HOST:
      break

    # Backoff sleep if set
    if host_state.backoff > 0:
      await asyncio.sleep(host_state.backoff)

    # Fetch (JS first if enabled)
    if use_js and playwright_ctx:
      status, f_url, ctype, html = await fetch_js(playwright_ctx, u, host_state)
      if not status and session:
        status, f_url, ctype, html = await fetch_http(session, u, host_state)
    else:
      status, f_url, ctype, html = await fetch_http(session, u, host_state)

    host_state.pages_count += 1

    # Handle failures & backoff
    if not status:
      host_state.consec_errors += 1
      continue
    if status in (429, 503):
      host_state.consec_errors += 1
      # backoff already set in fetch_http
      continue
    elif status == 403:
      host_state.consec_errors += 1
      # likely blocked; stop this host
      break
    elif status >= 400:
      host_state.consec_errors += 1
      continue
    else:
      # success; reset backoff + error count
      host_state.consec_errors = 0
      # backoff reset done in fetch_http/js on success

    if not final_url:
      final_url = f_url
      http_status = status

    # CAPTCHA check
    if is_captcha(html):
      host_state.consec_errors += 1
      host_state.captcha_hits += 1
      continue

    soup = BeautifulSoup(html, "html.parser")
    links = extract_links(soup)
    all_links.extend(links)  # Collect for external service URL extraction
    link_blob = "\n".join(links)
    text_blob = soup.get_text(separator=" ").lower()

    site_html.append(html)
    site_links.append(link_blob)
    site_texts.append(text_blob)

    if re.search(r"(patientviewer\.com|operadds\.com|WebForms\.html|/pay|/appointment|/forms?)",
                 html+link_blob, re.IGNORECASE):
      evidence_urls.append(f_url)

  combined = "\n".join(site_html + site_links + site_texts)

  # Booking/forms/pay detection
  booking_txt = re.search(r"\b(book online|schedule (now|online)|request (an )?appointment)\b", combined, re.I)
  forms_txt = re.search(r"\b(digital (patient )?forms?|paperless forms?|new patient form)\b", combined, re.I)
  pay_txt = re.search(r"\b(pay (your )?bill|online payment|text-to-pay)\b", combined, re.I)

  tp_booking = find_matches(third_patterns.get("booking", []), combined)
  tp_forms = find_matches(third_patterns.get("forms", []), combined)
  tp_pay = find_matches(third_patterns.get("payments", []), combined)
  tp_all = find_matches(third_patterns.get("all", []), combined)

  has_booking = bool(booking_txt or tp_booking)
  has_forms = bool(forms_txt or tp_forms)
  has_pay = bool(pay_txt or tp_pay)

  phone_hits = find_matches(phone_patterns.get("providers", []), combined)

  # PMS from site content only; job clues added later
  pms_guess_site, pms_conf_site, pms_clues_site, _ = score_pms(pms_patterns, combined, "")

  likely_booking_vendor = tp_booking[0] if tp_booking else ""
  likely_phone_provider = phone_hits[0] if phone_hits else ""

  # Extract external booking/payment/forms URLs
  practice_domain = urlparse(website).netloc if website else ""
  booking_urls, payment_urls, forms_urls = extract_external_service_urls(all_links, practice_domain)

  # Aggregate some host-level evidence samples
  for ev in evidence_urls[:3]:
    if len(host_state.evidence_urls_sample) < 5 and ev not in host_state.evidence_urls_sample:
      host_state.evidence_urls_sample.append(ev)

  return {
    "id": rid,
    "name": name,
    "website": website,
    "final_url": final_url,
    "http_status": http_status,

    # Online capabilities
    "has_online_booking": has_booking,
    "has_online_forms": has_forms,
    "has_online_payments": has_pay,

    # Third-party clues and "likely" vendor for booking
    "third_party_booking_clues": ";".join(tp_booking),
    "third_party_forms_clues": ";".join(tp_forms),
    "third_party_payments_clues": ";".join(tp_pay),
    "third_party_other_clues": ";".join(tp_all),
    "likely_booking_vendor": likely_booking_vendor,

    # Phone clues + likely
    "phone_clues_site": ";".join(phone_hits),
    "likely_phone_provider": likely_phone_provider,

    # PMS site-derived guess + evidence (job evidence added later)
    "pms_clues_site": ";".join(pms_clues_site),
    "likely_pms": pms_guess_site,
    "pms_confidence": pms_conf_site,

    # Evidence URLs we found
    "evidence_urls": ";".join(list(dict.fromkeys(evidence_urls))),

    # External service URLs (for post-analysis of vendors)
    "booking_urls": ";".join(booking_urls[:5]),  # Limit to 5 to keep CSV manageable
    "payment_urls": ";".join(payment_urls[:5]),
    "forms_urls": ";".join(forms_urls[:5]),
  }

async def run(in_path, out_csv, out_jsonl, global_concurrency, use_js, fail_alert_pct, domain_report_path=None):
  pms_patterns = load_yaml(Path("patterns/pms_patterns.yaml"))
  third_patterns = load_yaml(Path("patterns/third_party_patterns.yaml"))
  phone_patterns = load_yaml(Path("patterns/phone_patterns.yaml"))

  rows = []
  with open(in_path, "r", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
      rows.append(r)

  # Host states
  host_states = defaultdict(HostState)

  # Optional Playwright context
  playwright_ctx = None
  if use_js:
    try:
      from playwright.async_api import async_playwright
    except Exception as e:
      print("Playwright not installed. Run: python -m playwright install", file=sys.stderr)
      raise

  totals = {"attempted": 0, "success": 0, "failed": 0}

  # Define CSV fieldnames
  fieldnames = [
    "id","name","website","final_url","http_status",
    "has_online_booking","has_online_forms","has_online_payments",
    "third_party_booking_clues","third_party_forms_clues","third_party_payments_clues","third_party_other_clues",
    "likely_booking_vendor",
    "phone_clues_site","likely_phone_provider",
    "pms_clues_site","likely_pms","pms_confidence",
    "evidence_urls",
    "booking_urls","payment_urls","forms_urls"
  ]

  # Open output files at the START
  jsonl_file = None
  csv_file = None
  write_lock = threading.Lock()

  try:
    # Open files for incremental writing
    jsonl_file = open(out_jsonl, "w", encoding="utf-8")
    csv_file = open(out_csv, "w", newline="", encoding="utf-8")
    csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    csv_writer.writeheader()
    csv_file.flush()  # Ensure header is written immediately

    connector = aiohttp.TCPConnector(limit=global_concurrency, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
      if use_js:
        async with async_playwright() as pw:
          browser = await pw.chromium.launch(headless=True)
          playwright_ctx = {"browser": browser, "timeout": 15000}
          tasks = [audit_site(session, r, pms_patterns, third_patterns, phone_patterns, use_js, playwright_ctx, host_states)
                   for r in rows if r.get("website")]
          for i in range(0, len(tasks), 150):
            chunk = tasks[i:i+150]
            partial = await asyncio.gather(*chunk)
            for it in partial:
              totals["attempted"] += 1
              if it and (it.get("http_status") or it.get("pms_clues_site") or it.get("third_party_booking_clues") or it.get("phone_clues_site")):
                # Write result immediately
                with write_lock:
                  jsonl_file.write(json.dumps(it, ensure_ascii=False) + "\n")
                  jsonl_file.flush()
                  csv_writer.writerow(it)
                  csv_file.flush()
                totals["success"] += 1
              else:
                totals["failed"] += 1

              # Progress update every 50 sites
              if totals["attempted"] % 50 == 0:
                print(f"[Progress] {totals['attempted']}/{len(tasks)} practices completed ({totals['attempted']/len(tasks)*100:.1f}%) - Success: {totals['success']}, Failed: {totals['failed']}", flush=True)
          await browser.close()
      else:
        tasks = [audit_site(session, r, pms_patterns, third_patterns, phone_patterns, False, None, host_states)
                 for r in rows if r.get("website")]
        for i in range(0, len(tasks), 200):
          chunk = tasks[i:i+200]
          partial = await asyncio.gather(*chunk)
          for it in partial:
            totals["attempted"] += 1
            if it and (it.get("http_status") or it.get("pms_clues_site") or it.get("third_party_booking_clues") or it.get("phone_clues_site")):
              # Write result immediately
              with write_lock:
                jsonl_file.write(json.dumps(it, ensure_ascii=False) + "\n")
                jsonl_file.flush()
                csv_writer.writerow(it)
                csv_file.flush()
              totals["success"] += 1
            else:
              totals["failed"] += 1

            # Progress update every 50 sites
            if totals["attempted"] % 50 == 0:
              print(f"[Progress] {totals['attempted']}/{len(tasks)} practices completed ({totals['attempted']/len(tasks)*100:.1f}%) - Success: {totals['success']}, Failed: {totals['failed']}", flush=True)

  finally:
    # Ensure files are closed properly
    if jsonl_file:
      jsonl_file.close()
    if csv_file:
      csv_file.close()

  # Alert on failure rate
  fail_rate = (100.0 * totals["failed"] / max(1, totals["attempted"]))
  msg = f"[Crawler Report] Attempted={totals['attempted']} Success={totals['success']} Failed={totals['failed']} FailRate={fail_rate:.2f}%"
  print(msg)
  if fail_rate >= fail_alert_pct:
    warn = f"ALERT: High failure rate ({fail_rate:.2f}%) >= threshold ({fail_alert_pct}%). Consider reducing concurrency, increasing delays, or disabling --use-js."
    print(warn, file=sys.stderr)
    alert_path = Path(out_csv).parent / "crawl_alert.txt"
    with open(alert_path, "w", encoding="utf-8") as af:
      af.write(msg + "\n" + warn + "\n")

  # Per-domain mini-report CSV
  if domain_report_path:
    cols = ["host","pages_attempted","pages_fetched","http_2xx","http_403","http_429","http_5xx","other_4xx",
            "captcha_hits","disallowed_paths","consec_errors_final","backoff_seconds_max","pages_count",
            "robots_crawl_delay","robots_cached","sample_evidence_urls"]
    with open(domain_report_path, "w", newline="", encoding="utf-8") as f:
      w = csv.DictWriter(f, fieldnames=cols)
      w.writeheader()
      for host, hs in host_states.items():
        w.writerow({
          "host": host,
          "pages_attempted": hs.pages_attempted,
          "pages_fetched": hs.pages_fetched,
          "http_2xx": hs.http_2xx,
          "http_403": hs.http_403,
          "http_429": hs.http_429,
          "http_5xx": hs.http_5xx,
          "other_4xx": hs.other_4xx,
          "captcha_hits": hs.captcha_hits,
          "disallowed_paths": hs.disallowed_paths,
          "consec_errors_final": hs.consec_errors,
          "backoff_seconds_max": hs.backoff,
          "pages_count": hs.pages_count,
          "robots_crawl_delay": hs.crawl_delay if hs.crawl_delay is not None else "",
          "robots_cached": "yes" if hs.robots_fetch_time > 0 else "no",
          "sample_evidence_urls": ";".join(hs.evidence_urls_sample)
        })
    print(f"[Crawler Report] Wrote per-domain report to {domain_report_path}")

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--in", dest="in_path", required=True)
  ap.add_argument("--out-csv", required=True)
  ap.add_argument("--out-jsonl", required=True)
  ap.add_argument("--concurrency", type=int, default=GLOBAL_CONCURRENCY_DEFAULT, help="Global concurrency (default 10)")
  ap.add_argument("--use-js", action="store_true", help="Enable Playwright JS rendering")
  ap.add_argument("--fail-alert-pct", type=float, default=FAIL_ALERT_PCT_DEFAULT, help="Alert threshold for failure rate (default 15%%)")
  ap.add_argument("--per-domain-report", dest="domain_report_path", default=None, help="Write per-domain metrics CSV here")
  args = ap.parse_args()
  asyncio.run(run(args.in_path, args.out_csv, args.out_jsonl, args.concurrency, use_js=args.use_js, fail_alert_pct=args.fail_alert_pct, domain_report_path=args.domain_report_path))

if __name__ == "__main__":
  main()

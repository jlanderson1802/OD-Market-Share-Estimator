#!/usr/bin/env python3
import argparse, pandas as pd, json

def pct(n, d):
  return round(100.0*n/max(1,d), 2)

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--in", required=True, help="results or enriched CSV")
  ap.add_argument("--out-json", required=True)
  ap.add_argument("--out-csv", required=True)
  args = ap.parse_args()

  df = pd.read_csv(args.in)
  n = len(df)

  metrics = {}
  metrics["num_practices"] = n
  metrics["pct_online_booking"] = pct((df["has_online_booking"]==True).sum(), n)
  metrics["pct_online_payments"] = pct((df["has_online_payments"]==True).sum(), n)
  metrics["pct_online_forms"] = pct((df["has_online_forms"]==True).sum(), n)

  pms_counts = df["likely_pms"].fillna("unknown").value_counts().to_dict()
  metrics["pms_distribution_pct"] = {k: pct(v, n) for k, v in pms_counts.items()}

  def any_nonempty(col):
    return (df[col].astype(str).str.len() > 0).sum()
  metrics["pct_third_party_booking"] = pct(any_nonempty("third_party_booking_clues"), n)
  metrics["pct_third_party_forms"] = pct(any_nonempty("third_party_forms_clues"), n)
  metrics["pct_third_party_payments"] = pct(any_nonempty("third_party_payments_clues"), n)

  phone_flat = df["phone_clues_site"].fillna("")
  providers = {}
  for v in phone_flat:
    for p in [x.strip() for x in str(v).split(";") if x.strip()]:
      providers[p] = providers.get(p, 0) + 1
  metrics["phone_providers_pct"] = {k: pct(v, n) for k, v in sorted(providers.items(), key=lambda x: -x[1])}

  with open(args.out_json, "w", encoding="utf-8") as f:
    json.dump(metrics, f, indent=2)
  rows = []
  for k, v in metrics.items():
    rows.append({"metric": k, "value": json.dumps(v) if isinstance(v, dict) else v})
  pd.DataFrame(rows).to_csv(args.out_csv, index=False)

  print("=== Summary ===")
  print(json.dumps(metrics, indent=2))

if __name__ == "__main__":
  main()

#!/usr/bin/env python3
"""
Analyze vendor distribution from crawl results.
Breaks down booking, payment, and forms vendors by frequency.
"""

import pandas as pd
from collections import Counter
import re
from urllib.parse import urlparse

def extract_vendor_from_url(url):
    """Extract vendor name from URL domain."""
    if not url or pd.isna(url):
        return None

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Map domains to vendor names
        vendor_mapping = {
            'nexhealth': 'NexHealth',
            'zocdoc': 'Zocdoc',
            'localmed': 'LocalMed',
            'getweave': 'Weave',
            'dental4.me': 'Flex/Curve Dental',
            'patientviewer': 'Open Dental',
            'swellcx': 'Swell',
            'carestack': 'CareStack',
            'ident.ws': 'iDent',
            'securehealthform': 'SecureHealthForm',
            'square': 'Square',
            'carecredit': 'CareCredit',
            'stripe': 'Stripe',
            'rectanglehealth': 'Rectangle Health',
            'jotform': 'JotForm',
            'typeform': 'Typeform',
            'gravityforms': 'Gravity Forms',
            'intakeq': 'IntakeQ',
            'facebook': None,  # Ignore social media
            'twitter': None,
            'instagram': None,
            'youtube': None,
        }

        for key, vendor in vendor_mapping.items():
            if key in domain:
                return vendor

        # If no match, return the domain
        return domain
    except:
        return None

def parse_url_list(url_string):
    """Parse semicolon-separated URLs."""
    if not url_string or pd.isna(url_string):
        return []
    return [u.strip() for u in str(url_string).split(';') if u.strip()]

def main():
    # Read results
    df = pd.read_csv('data/results.csv')

    print(f"Total practices analyzed: {len(df)}")
    print(f"Practices with data (status 200): {len(df[df['http_status'] == 200])}\n")

    # Analyze booking vendors
    print("=" * 60)
    print("BOOKING VENDORS")
    print("=" * 60)

    booking_vendors = []
    for urls in df['booking_urls'].dropna():
        for url in parse_url_list(urls):
            vendor = extract_vendor_from_url(url)
            if vendor:
                booking_vendors.append(vendor)

    booking_counter = Counter(booking_vendors)
    total_booking = len(df[df['has_online_booking'] == True])
    print(f"\nTotal practices with online booking: {total_booking}")
    print(f"Vendor breakdown (from {len(booking_vendors)} URLs captured):\n")
    for vendor, count in booking_counter.most_common(15):
        print(f"  {vendor:30} {count:4} URLs")

    # Analyze payment vendors
    print("\n" + "=" * 60)
    print("PAYMENT VENDORS")
    print("=" * 60)

    payment_vendors = []
    for urls in df['payment_urls'].dropna():
        for url in parse_url_list(urls):
            vendor = extract_vendor_from_url(url)
            if vendor:
                payment_vendors.append(vendor)

    payment_counter = Counter(payment_vendors)
    total_payment = len(df[df['has_online_payments'] == True])
    print(f"\nTotal practices with online payments: {total_payment}")
    print(f"Vendor breakdown (from {len(payment_vendors)} URLs captured):\n")
    for vendor, count in payment_counter.most_common(15):
        print(f"  {vendor:30} {count:4} URLs")

    # Analyze forms vendors
    print("\n" + "=" * 60)
    print("FORMS VENDORS")
    print("=" * 60)

    forms_vendors = []
    for urls in df['forms_urls'].dropna():
        for url in parse_url_list(urls):
            vendor = extract_vendor_from_url(url)
            if vendor:
                forms_vendors.append(vendor)

    forms_counter = Counter(forms_vendors)
    total_forms = len(df[df['has_online_forms'] == True])
    print(f"\nTotal practices with online forms: {total_forms}")
    print(f"Vendor breakdown (from {len(forms_vendors)} URLs captured):\n")
    for vendor, count in forms_counter.most_common(15):
        print(f"  {vendor:30} {count:4} URLs")

    # Analyze third-party clues (text matches)
    print("\n" + "=" * 60)
    print("THIRD-PARTY CLUES (from page content)")
    print("=" * 60)

    # Booking clues
    booking_clues = []
    for clue in df['third_party_booking_clues'].dropna():
        booking_clues.extend([c.strip() for c in str(clue).split(',') if c.strip()])

    if booking_clues:
        print(f"\nBooking mentions (from {len(booking_clues)} detections):")
        for clue, count in Counter(booking_clues).most_common(10):
            print(f"  {clue:30} {count:4}x")

    # Payment clues
    payment_clues = []
    for clue in df['third_party_payments_clues'].dropna():
        payment_clues.extend([c.strip() for c in str(clue).split(',') if c.strip()])

    if payment_clues:
        print(f"\nPayment mentions (from {len(payment_clues)} detections):")
        for clue, count in Counter(payment_clues).most_common(10):
            print(f"  {clue:30} {count:4}x")

    # Forms clues
    forms_clues = []
    for clue in df['third_party_forms_clues'].dropna():
        forms_clues.extend([c.strip() for c in str(clue).split(',') if c.strip()])

    if forms_clues:
        print(f"\nForms mentions (from {len(forms_clues)} detections):")
        for clue, count in Counter(forms_clues).most_common(10):
            print(f"  {clue:30} {count:4}x")

    # Top practices with most integrations
    print("\n" + "=" * 60)
    print("SAMPLE: PRACTICES WITH MOST EXTERNAL INTEGRATIONS")
    print("=" * 60)

    df['integration_count'] = (
        df['has_online_booking'].astype(int) +
        df['has_online_payments'].astype(int) +
        df['has_online_forms'].astype(int)
    )

    top_practices = df[df['integration_count'] >= 2].sort_values('integration_count', ascending=False).head(10)

    for _, row in top_practices.iterrows():
        print(f"\n{row['name']}")
        print(f"  Website: {row['website']}")
        if row['has_online_booking']:
            print(f"  Booking: {row['likely_booking_vendor'] if pd.notna(row['likely_booking_vendor']) else 'detected'}")
        if row['has_online_payments']:
            print(f"  Payments: detected")
        if row['has_online_forms']:
            print(f"  Forms: detected")

if __name__ == '__main__':
    main()

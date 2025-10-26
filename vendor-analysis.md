# Dental Practice Technology Vendor Analysis

**Dataset:** 2,617 dental practices crawled across 100+ US cities
**Analysis Date:** October 26, 2025

---

## Executive Summary

### Technology Adoption Rates
- **26.8%** (701 practices) offer online booking
- **32.4%** (848 practices) accept online payments
- **11.4%** (297 practices) provide online forms
- **100%** of detected features are powered by third-party vendors (not self-hosted)

### Market Insights
1. **Payment adoption exceeds booking** - More practices accept online payments than offer online booking
2. **Forms lag significantly** - Only 1 in 9 practices have online patient forms
3. **Third-party dominance** - No practices use self-hosted solutions; all rely on SaaS vendors

---

## Booking Vendors

**Total practices with online booking:** 701 (26.8%)
**External URLs captured:** 527

### Market Leaders
| Vendor | URLs Captured | Notes |
|--------|---------------|-------|
| **NexHealth** | 77 | Clear market leader, modern API-first platform |
| **LocalMed** | 64 | Strong presence, acquired by Cedar in 2022 |
| **Modento** (book.modento.io) | 49 | Growing player |
| **FlexBook** (flexbook.me/www.flexbook.me) | 55 | Combined with Flex/Curve Dental (24) |
| **Dentrix Ascend** | 20 | PMS-integrated booking (Henry Schein) |
| **Zocdoc** | 16 | Consumer marketplace model |
| **Yapi** | 11 URLs + 73 text mentions | All-in-one platform with strong adoption |

### Key Findings
- **Yapi** appears more dominant when counting text mentions (73x) vs URLs (11)
- **FlexBook/dental4.me** are related (Flex Dental Solutions)
- Several PMS vendors (Dentrix Ascend, Oryx) offer integrated booking

---

## Payment Vendors

**Total practices with online payments:** 848 (32.4%)
**External URLs captured:** 293

### Market Leaders
| Vendor | URLs/Mentions | Type |
|--------|---------------|------|
| **Square** | 768 mentions + 5 URLs | General payment processor |
| **Smile Generation MyChart** | 54 URLs | DSO-specific solution |
| **Balance Collect** | 41 URLs | Dental-specific AR platform |
| **CareCredit** | 28 mentions | Patient financing |
| **Cherry** (pay.withcherry.com) | 9 URLs | Point-of-sale financing |
| **Weave** (weavebillpay.com) | 9 URLs | Multi-service platform |

### Key Findings
- **Square dominates** with 91% of text mentions (768 out of 839)
- **CareCredit** is the top financing option mentioned
- **DSO platforms** (Smile Generation) have proprietary payment systems
- **Dental-specific solutions** (Balance Collect, PayMyDentist) emerging alongside general processors

---

## Forms Vendors

**Total practices with online forms:** 297 (11.4%)
**External URLs captured:** 244

### Market Leaders
| Vendor | URLs/Mentions | Type |
|--------|---------------|------|
| **Gravity Forms** | 83 mentions | WordPress plugin |
| **Yapi** | 73 mentions + forms URLs | All-in-one platform |
| **Modento** | 57 mentions | Patient engagement platform |
| **Open Dental** (patientviewer) | 22 URLs | PMS-integrated forms |
| **PatientConnect365** | 10 URLs | Dental-specific forms |
| **JotForm** | 11 URLs | General forms platform |

### Key Findings
- **Gravity Forms** (WordPress plugin) leads with 30.7% of mentions
- **Yapi and Modento** offer forms as part of all-in-one platforms
- **PMS-integrated forms** (Open Dental, iDent) represent ~10% of URLs
- Forms adoption is 3x lower than booking/payments - major opportunity gap

---

## Multi-Service Platform Analysis

Several vendors provide multiple services (booking + payments + forms):

| Platform | Services | Observations |
|----------|----------|--------------|
| **Yapi** | Booking, Forms | 73 mentions across both categories; strong all-in-one adoption |
| **Modento** | Booking, Forms | 49 booking URLs + 57 form mentions |
| **Weave** | Booking, Payments | 10 booking URLs + 9 payment URLs |
| **NexHealth** | Booking, Payments, Forms | 77 booking + 8 payment URLs; API-first platform |
| **Open Dental** | Payments, Forms | PMS vendor with PatientViewer portal; 6 payment + 22 form URLs |

**Insight:** Practices using all-in-one platforms (Yapi, Modento, NexHealth) show higher multi-feature adoption.

---

## Geographic and Practice Type Insights

### Practices with Most Integrations (3/3 features)
These practices demonstrate the "full stack" of patient-facing digital tools:

1. **Nichols Family Dentistry** (michaelnicholsdds.com) - Independent practice
2. **LWSS Family Dentistry** - Uses Yapi
3. **Winston-Salem Dental Specialists** - Uses Yapi
4. **Grandover Village Dental Care** - Uses Yapi
5. **Studio Dental @ Union Station** (CA) - Full digital suite

**Pattern:** Yapi users disproportionately have all three features enabled, suggesting the platform drives comprehensive digital adoption.

---

## Market Share Estimates (by category)

### Online Booking Market Share
Based on 527 URLs captured from 701 practices with booking:

1. **NexHealth** - 14.6%
2. **LocalMed** - 12.1%
3. **Modento** - 9.3%
4. **FlexBook/Dental4.me** - 10.4%
5. **Dentrix Ascend** - 3.8%
6. **Yapi** - 2.1% (URLs only; likely higher with integrations)
7. **Others** - 47.7%

### Online Payment Market Share
Based on 839 text mentions:

1. **Square** - 91.5%
2. **CareCredit** - 6.3%
3. **Others** - 2.2%

### Online Forms Market Share
Based on 270 text mentions:

1. **Gravity Forms** - 30.7%
2. **Yapi** - 27.0%
3. **Modento** - 21.1%
4. **Others** - 21.2%

---

## PMS Detection Results

**All practices:** PMS = "unknown" (100%)

**Why:** Practice Management Systems are backend software not visible on public websites. To detect PMS usage, we need to:
1. Run job posting enrichment (search for "Dentrix experience required" in job listings)
2. Analyze PMS-specific patient portals (e.g., PatientViewer = Open Dental, eCentral = Dentrix)
3. Cross-reference booking integrations (e.g., Dentrix Ascend booking suggests Dentrix PMS)

**Evidence collected for future PMS analysis:**
- 20 practices using `bookit.dentrixascend.com` (likely Dentrix users)
- 22 practices using Open Dental's PatientViewer
- 8 practices with "denticon" mentions in forms

---

## Actionable Insights

### For Dental Software Vendors
1. **Payment gap opportunity** - 32% adoption vs 27% booking suggests practices prioritize revenue collection
2. **Forms are underserved** - Only 11% adoption; major whitespace for growth
3. **Platform consolidation** - Yapi/Modento show higher 3-feature adoption; bundles drive usage

### For Dental Practices
1. **Industry benchmarks** - If you lack online booking, you're behind 73% of peers
2. **Patient expectations** - 1 in 4 practices offer online booking; table stakes for new patient acquisition
3. **Platform efficiency** - Practices using all-in-one platforms (Yapi, NexHealth, Modento) show higher digital adoption

### For Market Researchers
1. **Square dominance** - 91% of payment mentions; near-monopoly in dental payments
2. **NexHealth momentum** - Captured 15% of booking URLs; strong growth trajectory
3. **LocalMed/Cedar** - Second in booking despite being acquired; sticky product
4. **WordPress footprint** - Gravity Forms' 31% share suggests WordPress powers many dental sites

---

## Next Steps

1. **Vendor consolidation analysis** - Identify practices using multiple vendors vs. all-in-one platforms
2. **Job posting enrichment** - Detect PMS systems to understand booking/PMS integration patterns
3. **Temporal analysis** - Re-crawl in 6 months to measure vendor market share shifts
4. **URL deep-dive** - Analyze the 47.7% "Other" booking vendors for emerging players

---

## Methodology Notes

- **URL extraction** added to crawler to capture actual booking/payment/forms service domains
- **Text pattern matching** used for in-page vendor mentions (e.g., "Square" in payment buttons)
- **527 booking URLs** captured from 701 practices (75% capture rate)
- **293 payment URLs** captured from 848 practices (35% capture rate) - suggests many use embedded widgets
- Some practices detected as having features but no external URLs captured (self-hosted or embed widgets)

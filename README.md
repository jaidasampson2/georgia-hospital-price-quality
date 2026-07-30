# Georgia Hospital Price & Quality Explorer — Data Documentation

An end-to-end analysis of hospital prices and quality measures across
Georgia, using hospitals' federally-mandated machine-readable pricing
files (MRFs) alongside CMS hospital quality data.

## Hospitals in This Project

| Hospital | City | Source Format | CCN | Status |
|---|---|---|---|---|
| Emory University Hospital | Atlanta | CSV (flat) | 110010 | Fully loaded |
| Grady Memorial Hospital | Atlanta | CSV (wide/pivoted) | 110079 | Fully loaded |
| Northside Hospital Atlanta | Atlanta | JSON (nested) | 110161 | Fully loaded |
| Piedmont Atlanta Hospital | Atlanta | ZIP → CSV (flat) | 110083 | Fully loaded |
| Wellstar Kennestone Hospital | Marietta | CSV (flat) | 110035 | Fully loaded |
| Arthur M. Blank Hospital (CHOA) | Atlanta | CSV (flat) | 113300 | Fully loaded |

CCN = CMS Certification Number, looked up by hand via CMS.gov / Care
Compare listings for each hospital, used to join pricing data to CMS
quality measures.

## Target Procedures

| Procedure | Codes Used | Notes |
|---|---|---|
| Head/Brain CT (no contrast) | CPT/HCPCS 70450 | |
| Knee MRI (no contrast) | CPT/HCPCS 73721 | |
| Colonoscopy | CPT/HCPCS 45378 **and** 45380 | See "Colonoscopy code variants" below |
| Cardiac Stress Test | CPT/HCPCS 93017 | See caveat under Price vs. Quality Analysis |

## Data Pipeline Structure

- **`data/raw/`** — Full, untouched source files as downloaded directly
  from each hospital. Excluded from version control via `.gitignore`
  (50MB–900MB+ each).
- **`data/sample/`** — Targeted excerpts of each hospital's raw file,
  containing only rows matching one of the four target procedure codes.
- **`data/processed/`** — Output of `src/flatten_*.py`, mapping each
  hospital's raw structure onto the unified schema described below.
- **`data/hospital_prices.db`** — Normalized SQLite database (gitignored;
  regenerate locally via `sql/schema.sql` + `src/load_database.py`).

## Sampling Methodology

**Random samples don't work for cross-hospital comparison.** An early
approach pulling the first 25 rows from each hospital's file produced
zero overlapping services across all six hospitals. `src/sample_by_code.py`
(CSV-based hospitals) and `src/sample_northside_by_code.py` (Northside's
JSON) instead stream through each hospital's **entire** raw file and
keep only rows matching a specific billing code + code type, capped at
200 matches per search. None of the searches in this project hit that
cap — every match count reflects a hospital's complete published data
for that code.

### Database loading: `--append` mode

Because each procedure search overwrites the same sample files,
`src/load_database.py` needed an `--append` flag to avoid wiping
previously-loaded procedures. Usage:

    python3 src/load_database.py            # full reset
    python3 src/load_database.py --append    # add without wiping existing rows

## Unified Output Schema

| Column | Description |
|---|---|
| `hospital_name` | Hospital this record belongs to |
| `description` | Service/item description as published |
| `ndc_code`, `revenue_code`, `cdm_code`, `hcpcs_code`, `cpt_code`, `drg_code` | Billing codes, routed by type. Unmapped types (`APC`, `LOCAL`) are dropped rather than guessed into the wrong column. |
| `billing_class` | `facility`, `professional`, or blank |
| `modifiers` | e.g. `26` (professional interpretation only) or `TC` (technical component only) |
| `drug_unit`, `drug_unit_type` | Only populated for drug/medication line items |
| `setting` | inpatient / outpatient |
| `gross_charge`, `discounted_cash`, `minimum_charge`, `maximum_charge` | Published charge figures |
| `payer_name`, `plan_name` | The specific payer + plan this row's rate applies to |
| `negotiated_price` | Exact negotiated dollar amount, only when published directly |
| `negotiated_percentage` | Percent-of-billed-charges rate, when used instead of a dollar amount |
| `median_amount` | Historical median claims amount, when published instead of/alongside a negotiated dollar amount |
| `price_type` | Labels what kind of number `resolved_price` is |
| `resolved_price` | Best available usable price estimate |
| `methodology` | Hospital's stated pricing methodology for this rate |

### `resolved_price` / `price_type` priority order

1. Clean negotiated dollar amount exists -> use it. `price_type = "negotiated_dollar"`
2. Else, percentage + gross charge both exist -> estimate `gross_charge x percentage / 100`. `price_type = "percent_of_billed"`
3. Else, median claims amount exists -> use it. `price_type = "median_estimate"`
4. Else -> `price_type = "unavailable"`, `resolved_price` blank.

## Key Data Quality Findings

### 1. Identical CPT code + description can mean genuinely different services (billing_class)

Grady's Head CT data showed five different prices for what looked like
one identical service. The file separately bills **facility** ($105.81),
**professional, modifier 26** (interpretation only, $38.95), and
**professional, modifier TC** (technical component only, $66.15) —
legitimately different billing entities sharing one CPT code. Only
Grady splits this way among the six hospitals. **All cross-hospital
price comparisons in this project exclude billing_class = 'professional'
rows.**

### 2. The same procedure code can be labeled a different "code type" across hospitals

Emory and Wellstar returned zero matches under CPT for all four target
procedures because neither hospital uses the label "CPT" anywhere in
their files — both label the same codes HCPCS instead. Re-searching
under HCPCS recovered real data for both. **Any cross-hospital query
must check both cpt_code and hcpcs_code.**

### 3. Colonoscopy code variants (45378 vs. 45380)

Piedmont had zero data under CPT 45378 (diagnostic-only) but
substantial data under 45380 (colonoscopy with biopsy) — the more
common real-world billing code. Both codes were searched and loaded
for every hospital. CHOA (pediatric) has neither — a genuine, expected
absence.

### 4. Outliers require median, not average, for honest comparison

A $50,000 "colonoscopy" rate at Northside (payer: CHAMPUS VA), ~9x the
next highest rate in the dataset, distorted average-based comparisons.
**All final price comparisons use median, not average.**

### 5. Emory and Wellstar's low prices are partly, but not fully, explained by payer mix

Their samples (12-38 observations) are dominated by Medicare Advantage
payers. Excluding Medicare-branded payers raised their medians
meaningfully but didn't close the gap to other hospitals, and the
remaining commercial-only samples (n=2 to n=10) are too small to be
reliable. **Conclusion: insufficient commercial-payer data published by
these two hospitals for these procedures to determine their true
typical price with confidence, in either direction.**

## Median Price Comparison (facility-only, outlier-resistant, all payers)

Query: `sql/median_by_procedure.sql`

| Hospital | Head CT | Knee MRI | Colonoscopy | Cardiac Stress |
|---|---|---|---|---|
| Grady | $627.65 | $1,116.25 | $1,362.00 | $2,100.81 |
| Piedmont | $654.50 | $1,754.00 | $3,455.76 | $2,484.90 |
| CHOA | $1,721.85 | $3,664.81 | n/a | $2,053.61 |
| Northside | $1,134.50 | $1,678.00 | $667.96 | $888.77 |
| Emory (see Finding 5) | $129.13 | $270.72 | $3,051.00 | $223.07 |
| Wellstar (see Finding 5) | $177.60 | $407.33 | $1,995.27 | $386.00 |

## Price vs. Quality Analysis

### Methodology

`src/fetch_cms_quality.py` pulls each hospital's quality data from
CMS's "Hospital General Information" dataset (xubh-q36u — the same
data behind Care Compare's star ratings), matched by CCN. It downloads
the full national CSV once and filters locally, after the dataset's
server-side query API returned unreliable 400 errors on filtered
requests.

**CHOA (Arthur M. Blank Hospital) has no CMS quality rating at all.**
CMS's standard adult hospital quality reporting program largely
excludes pediatric hospitals — confirmed directly in the data (every
measure returns "Not Available"). CHOA is excluded from all
price-vs-quality comparisons below.

**Emory and Wellstar are also excluded from this analysis specifically**
(despite having star ratings), because their price data is already
flagged as low-confidence (Finding 5) — comparing an unreliable price
against a real quality rating would produce a misleading result.

This leaves **3 hospitals** with both reliable price data and a
standard CMS rating: Grady (2★), Northside (3★), Piedmont (4★).

### Overall star rating vs. median price, by procedure

| Procedure | Grady (2★) | Northside (3★) | Piedmont (4★) | Rating predicts price? |
|---|---|---|---|---|
| Head CT | $627.65 | $1,134.50 | $654.50 | No |
| Knee MRI | $1,116.25 | $1,678.00 | $1,754.00 | Yes |
| Colonoscopy | $1,362.00 | $667.96 | $3,455.76 | No |
| Cardiac Stress Test¹ | $2,100.81 | $888.77 | $2,484.90 | No |

¹ Grady's cardiac stress test rows are labeled "Stress Echo," which
typically denotes a combined stress test + echocardiogram (usually
billed under different CPT codes, e.g. 93350/93351) rather than the
tracing-only service CPT 93017 specifically denotes. This may not be a
fully comparable service to the other hospitals' rows under this code —
a data quality caveat, not a corrected result.

**Only 1 of 4 procedures (Knee MRI) shows higher rating predicting
higher price.** With only 3 comparable hospitals, this dataset does not
support a price-quality relationship in either direction.

### Component-level quality measures complicate the picture further

Rather than relying on the single blended star rating, a supplementary
query broke out CMS's underlying safety and readmission measure counts:

| Hospital | Overall Rating | Safety Measures "Better" | Readmission Measures "Better" |
|---|---|---|---|
| Emory | 4★ | 1 of 8 | 1 of 11 |
| Piedmont | 4★ | 4 of 8 | 0 of 11 |
| Wellstar | 4★ | 4 of 8 | 1 of 11 |
| Northside | 3★ | 1 of 8 | 0 of 10 |
| Grady | 2★ | **3 of 7** | 0 of 8 |

**Grady — the lowest overall-rated hospital in this project — actually
outperforms both Northside and Emory on the specific safety measure
count** (43% "better than national average" vs. 12% for the other two).
Grady's low composite rating appears to be driven primarily by weak
readmission performance (0 of 8 "better," in line with most hospitals
in this dataset, so not especially distinguishing) rather than
uniformly lower quality of care.

### Conclusion

This dataset does not support treating a hospital's overall star rating
as a reliable proxy for either price or quality on a per-component
basis. Prices did not consistently track star ratings across
procedures (1 of 4 matched), and a hospital's composite rating can mask
meaningfully different performance across its individual quality
dimensions — a lower-rated hospital (Grady) scored better than
higher-rated peers on a specific, real safety metric. With only 3
hospitals carrying both reliable price data and a standard CMS rating,
this sample is also too small to detect a genuine relationship even if
one exists at a larger scale.

## How to Reproduce

1. Install dependencies: `pip install -r requirements.txt --break-system-packages`
2. Search a hospital's full raw file for a procedure code:
   `python3 src/sample_by_code.py "<Hospital Name>" <code> <CPT|HCPCS>`
   (or `src/sample_northside_by_code.py <code> <type>` for Northside)
3. Flatten into the unified schema: `python3 src/flatten_<hospital>_sample.py`
4. Load into the database: `python3 src/load_database.py --append`
5. Fetch CMS quality measures: `python3 src/fetch_cms_quality.py`
6. Recreate the database from scratch if needed:
   `rm data/hospital_prices.db && sqlite3 data/hospital_prices.db < sql/schema.sql`

## Next Steps

- Build the Tableau/Power BI dashboard incorporating the median-vs-
  average, sample-size, and price-quality caveats documented above.
- Consider pulling procedure-specific CMS measures (e.g. imaging
  efficiency measures, where still tracked) if a more targeted quality
  comparison is wanted, with the understanding that CMS's standard
  measure set is largely inpatient-focused and doesn't map cleanly onto
  this project's four (mostly outpatient) target procedures.
- Emory/Wellstar's commercial-payer data gap (Finding 5) is a genuine,
  documented limitation of their published files, not something to
  "fix" further within this project's data source.
# Georgia Hospital Price & Quality Explorer — Data Documentation

An end-to-end analysis of hospital prices and quality measures across
Georgia, using hospitals' federally-mandated machine-readable pricing
files (MRFs) alongside CMS hospital quality data.

## Hospitals in This Project

| Hospital | City | Source Format | Status |
|---|---|---|---|
| Emory University Hospital | Atlanta | CSV (flat) | Fully loaded |
| Grady Memorial Hospital | Atlanta | CSV (wide/pivoted) | Fully loaded |
| Northside Hospital Atlanta | Atlanta | JSON (nested) | Fully loaded |
| Piedmont Atlanta Hospital | Atlanta | ZIP → CSV (flat) | Fully loaded |
| Wellstar Kennestone Hospital | Marietta | CSV (flat) | Fully loaded |
| Arthur M. Blank Hospital (CHOA) | Atlanta | CSV (flat) | Fully loaded |

## Target Procedures

Four procedures were selected as the project's comparison set, chosen
for having recognizable, common billing codes:

| Procedure | Codes Used | Notes |
|---|---|---|
| Head/Brain CT (no contrast) | CPT/HCPCS 70450 | |
| Knee MRI (no contrast) | CPT/HCPCS 73721 | |
| Colonoscopy | CPT/HCPCS 45378 **and** 45380 | See "Colonoscopy code variants" below |
| Cardiac Stress Test | CPT/HCPCS 93017 | |

## Data Pipeline Structure

- **`data/raw/`** — Full, untouched source files as downloaded directly
  from each hospital. Excluded from version control via `.gitignore`
  (50MB–900MB+ each).
- **`data/sample/`** — Targeted excerpts of each hospital's raw file,
  containing only rows matching one of the four target procedure codes
  (searched across the FULL raw file, not just the first N rows —
  see "Sampling Methodology" below).
- **`data/processed/`** — Output of `src/flatten_*.py`, mapping each
  hospital's raw structure onto the unified schema described below.
- **`data/hospital_prices.db`** — Normalized SQLite database (gitignored;
  regenerate locally via `sql/schema.sql` + `src/load_database.py`).

## Sampling Methodology

**Random samples don't work for cross-hospital comparison.** An early
approach pulling the first 25 rows from each hospital's file produced
zero overlapping services across all six hospitals — every hospital's
random slice landed on a different category of item (drugs, room
types, surgical supplies, DRG charges). Meaningful comparison requires
deliberately searching for the same procedure everywhere.

`src/sample_by_code.py` (CSV-based hospitals) and
`src/sample_northside_by_code.py` (Northside's JSON) instead stream
through each hospital's **entire** raw file and keep only rows matching
a specific billing code + code type, capped at 200 matches per search.
These scripts overwrite each hospital's `data/sample/*` file — sample
files represent "the last procedure searched for," not a fixed random
excerpt.

### Database loading: `--append` mode

Because each procedure search overwrites the same sample files,
`src/load_database.py` needed an `--append` flag to avoid wiping
previously-loaded procedures every time a new one was searched. Without
it, searching for Knee MRI after Head CT would delete the Head CT data
before loading Knee MRI. Usage:

    python3 src/load_database.py            # full reset
    python3 src/load_database.py --append    # add without wiping existing rows

## Unified Output Schema

| Column | Description |
|---|---|
| `hospital_name` | Hospital this record belongs to |
| `description` | Service/item description as published |
| `ndc_code`, `revenue_code`, `cdm_code`, `hcpcs_code`, `cpt_code`, `drg_code` | Billing codes, routed by type. Unmapped types (`APC`, `LOCAL`) are dropped rather than guessed into the wrong column. |
| `billing_class` | `facility`, `professional`, or blank — see billing_class finding below |
| `modifiers` | e.g. `26` (professional interpretation only) or `TC` (technical component only) |
| `drug_unit`, `drug_unit_type` | Only populated for drug/medication line items |
| `setting` | inpatient / outpatient |
| `gross_charge`, `discounted_cash`, `minimum_charge`, `maximum_charge` | Published charge figures |
| `payer_name`, `plan_name` | The specific payer + plan this row's rate applies to |
| `negotiated_price` | Exact negotiated dollar amount, only when published directly |
| `negotiated_percentage` | Percent-of-billed-charges rate, when used instead of a dollar amount |
| `median_amount` | Historical median claims amount, when published instead of/alongside a negotiated dollar amount |
| `price_type` | Labels what kind of number `resolved_price` is (see below) |
| `resolved_price` | Best available usable price estimate |
| `methodology` | Hospital's stated pricing methodology for this rate |

### `resolved_price` / `price_type` priority order

1. Clean negotiated dollar amount exists -> use it. `price_type = "negotiated_dollar"`
2. Else, percentage + gross charge both exist -> estimate `gross_charge x percentage / 100`. `price_type = "percent_of_billed"`
3. Else, median claims amount exists -> use it. `price_type = "median_estimate"`
4. Else -> `price_type = "unavailable"`, `resolved_price` blank.

## Key Data Quality Findings

### 1. Identical CPT code + description can mean genuinely different services (billing_class)

Investigating unexplained price variation for Grady's Head CT data
(five different prices for what looked like one identical service)
revealed the file separately bills:
- **facility** — the hospital's facility fee ($105.81)
- **professional, modifier 26** — physician interpretation only ($38.95)
- **professional, modifier TC** — technical component only ($66.15)

These are legitimately different billing entities sharing one CPT
code — standard U.S. medical billing practice, not a data error. Only
Grady splits this way among the six hospitals in this project (Emory
and Wellstar report facility only; Northside, Piedmont, and CHOA
report no billing_class split at all). **All cross-hospital price
comparisons in this project exclude billing_class = 'professional'
rows**, since no other hospital reports a comparable professional-fee
line, and including Grady's would silently compare a physician fee
against other hospitals' full facility charges.

### 2. The same procedure code can be labeled a different "code type" across hospitals

Emory and Wellstar returned **zero matches** across all four target
procedures when searched under CPT — not because they lack this
data, but because **neither hospital uses the label "CPT" anywhere in
their files.** A full code-type frequency scan (src/count_code_types.py)
showed both hospitals label the same codes HCPCS instead (CPT codes
are technically a subset of HCPCS Level I). Re-searching under
HCPCS recovered real data for both hospitals across all four
procedures. **Any cross-hospital query must check both cpt_code and
hcpcs_code** — filtering on one field alone will silently and
incorrectly exclude hospitals that label the same codes differently.

### 3. Colonoscopy code variants (45378 vs. 45380)

Piedmont returned zero matches for CPT 45378 (diagnostic-only
colonoscopy) but had substantial data under CPT 45380 (colonoscopy with
biopsy) — the more common real-world billing code, since most
colonoscopies performed clinically find and address something. To keep
the comparison fair, **both codes were searched and loaded for every
hospital**, rather than using a different code for one hospital only.
CHOA (pediatric) has neither code — a genuine, expected absence given
its patient population, not a data gap.

### 4. Outliers require median, not average, for honest comparison

Initial average-based comparisons were distorted by a small number of
extreme outlier rates — most notably a **$50,000 "colonoscopy" rate at
Northside** under the payer name CHAMPUS VA, roughly 9x the next
highest rate in the entire dataset. These are almost certainly
out-of-network/workers'-comp ceiling rates, not real negotiated prices.
**All final comparisons use median, not average**, since median is far
more resistant to this kind of extreme outlier without needing to
manually identify and exclude every suspicious payer by name.

### 5. Sample size varies enormously and affects reliability

| Hospital | Head CT (n) | Knee MRI (n) | Colonoscopy (n) | Cardiac Stress (n) |
|---|---|---|---|---|
| Grady | 48 | 48 | 56 | 516 |
| Piedmont | 18 | 16 | 36 | 90 |
| CHOA | 28 | 56 | 0 | 140 |
| Northside | 134 | 402 | 448 | 3,168 |
| Emory | 13 | 13 | 38 | 14 |
| Wellstar | 12 | 12 | 26 | 18 |

Emory and Wellstar's samples (12-38 rate observations per procedure)
are an order of magnitude smaller than Northside's (134-3,168). **Their
median prices are flagged as low-confidence**: both hospitals' small
samples happened to draw disproportionately from Medicare Advantage
payers (Devoted Health, BCBS Blue Value Secure, Cigna Healthspring,
etc.), which are structurally lower-cost than commercial insurance
industry-wide. Their low medians likely reflect **sample composition**,
not necessarily lower true facility prices, and would need a larger
sample (via MAX_MATCHES increase in sample_by_code.py) to confirm.

## Median Price Comparison (facility-only, outlier-resistant)

Query: `sql/median_by_procedure.sql`

| Hospital | Head CT | Knee MRI | Colonoscopy | Cardiac Stress |
|---|---|---|---|---|
| Grady | $627.65 | $1,116.25 | $1,362.00 | $2,100.81 |
| Piedmont | $654.50 | $1,754.00 | $3,455.76 | $2,484.90 |
| CHOA | $1,721.85 | $3,664.81 | n/a | $2,053.61 |
| Northside | $1,134.50 | $1,678.00 | $667.96 | $888.77 |
| Emory (low confidence) | $129.13 | $270.72 | $3,051.00 | $223.07 |
| Wellstar (low confidence) | $177.60 | $407.33 | $1,995.27 | $386.00 |

"Low confidence" = small, payer-skewed sample (see Finding 5).

## How to Reproduce

1. Install dependencies: `pip install -r requirements.txt --break-system-packages`
2. Search a hospital's full raw file for a procedure code:
   `python3 src/sample_by_code.py "<Hospital Name>" <code> <CPT|HCPCS>`
   (or `src/sample_northside_by_code.py <code> <type>` for Northside)
3. Flatten into the unified schema: `python3 src/flatten_<hospital>_sample.py`
4. Load into the database: `python3 src/load_database.py --append`
5. Recreate the database from scratch if needed:
   `rm data/hospital_prices.db && sqlite3 data/hospital_prices.db < sql/schema.sql`

## Next Steps

- Build the Tableau/Power BI dashboard comparing prices across hospitals
  and procedures, incorporating the median-vs-average and sample-size
  caveats documented above.
- Consider increasing MAX_MATCHES for Emory/Wellstar specifically to
  get a larger, more representative payer mix before finalizing
  comparisons.
- Integrate CMS hospital quality measures via the Provider Data Catalog
  API for the price-vs-quality analysis.
- Investigate CHOA's colonoscopy gap further (confirmed absent under
  both 45378 and 45380 — likely a genuine pediatric-population effect).
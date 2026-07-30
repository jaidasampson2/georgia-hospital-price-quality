# Georgia Hospital Price & Quality Explorer — Data Documentation

An end-to-end analysis of hospital prices and quality measures across
Georgia, using hospitals' federally-mandated machine-readable pricing
files (MRFs) alongside CMS hospital quality data.

## Hospitals in This Project

| Hospital | City | Source Format | Status |
|---|---|---|---|
| Emory University Hospital | Atlanta | CSV (flat) | Sampled + flattened |
| Grady Memorial Hospital | Atlanta | CSV (wide/pivoted) | Sampled + flattened |
| Northside Hospital Atlanta | Atlanta | JSON (nested) | Sampled + flattened |
| Piedmont Atlanta Hospital | Atlanta | ZIP → CSV (flat) | Sampled + flattened |
| Wellstar Kennestone Hospital | Marietta | CSV (flat) | Sampled + flattened |
| Arthur M. Blank Hospital (CHOA) | Atlanta | CSV (flat) | Sampled + flattened |

All six hospitals are fully sourced, sampled, and have working flattening
scripts producing a unified output schema. Source URLs are listed in
`config/hospitals.csv`.

## Data Pipeline Structure

This project moves data through three stages, represented by three folders:

- **`data/raw/`** — Full, untouched source files as downloaded directly
  from each hospital (or CMS). These are large (50MB–900MB+) and are
  excluded from version control via `.gitignore`. To download them
  locally, run `python3 src/download_files.py`.
- **`data/sample/`** — Small, truncated excerpts (typically 25 records)
  of each hospital's raw file, in its original untouched structure. These
  exist so the file structure can be inspected in GitHub's file viewer
  without downloading the full dataset. Produced by `src/sample_*.py`
  scripts, one per hospital.
- **`data/processed/`** — Output of the actual parsing/transformation
  logic: raw data reshaped into the unified schema described below.
  Produced by `src/flatten_*.py` scripts, one per hospital. Currently
  these run against the *sample* files; the same logic will later run
  against the full raw files via `src/parse_prices.py`.

## Retrieval Notes

- **Northside Hospital Atlanta**'s official machine-readable file returns
  HTTP 403 to automated Python requests, even with browser-like headers,
  due to CDN-level bot protection. The file was manually downloaded
  through a standard web browser and stored locally in `data/raw/`. This
  limitation is logged as a documented exception, not treated as a
  missing or invalid source — Northside is otherwise a fully compliant,
  high-quality data source (see findings below).
- **Piedmont Atlanta Hospital** distributes its pricing file as a ~75MB
  ZIP archive rather than a plain CSV. Because ZIP files store their
  table of contents at the end of the file, partial/streamed sampling
  isn't possible the way it is for plain CSVs. `src/sample_piedmont.py`
  downloads the full ZIP to a temporary location, extracts the sample,
  and deletes the temporary download immediately afterward — the full
  ZIP itself is never retained outside `data/raw/`.
- **Wellstar Kennestone** and **Wellstar Windy Hill** share the same EIN
  in their published filenames, despite being separate physical
  hospitals. All lookups in this project key off `hospital_name`, not
  EIN, to avoid collisions.

## Unified Output Schema

Every hospital's file uses a different raw structure (nested JSON, flat
CSV, or wide/pivoted CSV with payer+plan info stored sideways as
columns), but every `flatten_*.py` script maps its hospital's data onto
the same set of output columns, so all six can eventually be combined
into one SQL table:

| Column | Description |
|---|---|
| `hospital_name` | Hospital this record belongs to |
| `description` | Service/item description as published |
| `ndc_code`, `revenue_code`, `cdm_code`, `hcpcs_code`, `cpt_code`, `drg_code` | Billing codes, extracted from each hospital's code fields and routed by type. Unmapped code types (e.g. `APC`, `LOCAL`) are intentionally dropped rather than guessed into the wrong column. |
| `drug_unit`, `drug_unit_type` | Only populated for drug/medication line items |
| `setting` | inpatient / outpatient |
| `gross_charge`, `discounted_cash`, `minimum_charge`, `maximum_charge` | Published charge figures |
| `payer_name`, `plan_name` | The specific payer + plan this row's rate applies to |
| `negotiated_price` | The exact negotiated dollar amount, **only** when the hospital published one directly. Left blank otherwise (see `price_type` below). |
| `negotiated_percentage` | The percent-of-billed-charges rate, when that's how the hospital expressed the price instead of a dollar amount |
| `median_amount` | A historical median claims amount, when the hospital published one instead of (or alongside) a negotiated dollar amount |
| `price_type` | Labels what kind of number `resolved_price` actually is — see below |
| `resolved_price` | The best available usable price estimate |
| `methodology` | The hospital's stated pricing methodology for this rate |

### How `resolved_price` and `price_type` work

A meaningful share of hospital pricing data isn't published as a clean
dollar amount — some hospitals only publish a percentage of billed
charges, or a historical median, or bury the real rate inside a
free-text fee-schedule description. Rather than leaving those rows
blank or silently guessing, every flattener applies the same priority
order:

1. If a clean negotiated dollar amount exists → use it.
   `price_type = "negotiated_dollar"`
2. Else, if a percentage AND a gross charge both exist → estimate
   `gross_charge × percentage / 100`.
   `price_type = "percent_of_billed"`
3. Else, if a median claims amount exists → use it.
   `price_type = "median_estimate"`
4. Else → `price_type = "unavailable"`, `resolved_price` left blank.

This means `resolved_price` always tells you the best number available,
while `price_type` always tells you exactly how trustworthy/precise that
number is — an estimated price is never silently presented as if it were
an exact negotiated rate.

## Data Quality Findings (from 25–100 row samples per hospital)

| Hospital | Source Format | `negotiated_dollar` | `median_estimate` | `unavailable` |
|---|---|---|---|---|
| Arthur M. Blank (CHOA) | CSV, flat | 25 / 25 (100%) | 0 | 0 |
| Grady Memorial | CSV, wide/pivoted | 100 / 100 (100%) | 0 | 0 |
| Piedmont Atlanta | ZIP → CSV, flat | 25 / 25 (100%) | 0 | 0 |
| Northside Atlanta | JSON, nested | 2,870 / 2,889 (99.3%) | n/a¹ | 19 (0.7%) |
| Wellstar Kennestone | CSV, flat | 0 | 16 / 25 (64%) | 9 / 25 (36%) |
| Emory University | CSV, flat | 0 | 1 / 25 (4%) | 24 / 25 (96%) |

¹ Northside's JSON schema has no `median_amount` equivalent field at all
— a structural difference between the JSON and CSV templates, not a
data gap.

### Key takeaways

- **File format complexity does not predict data usability.** Grady's
  file uses the most complex structure in the dataset (payer/plan
  information spread sideways across 200+ columns, requiring a full
  wide-to-long unpivot), yet is 100% usable. Emory's file uses the
  simplest, flattest structure of any hospital, yet is 96% unusable for
  direct dollar-amount comparison.
- **Identical stated methodology does not guarantee identical
  usability.** Grady and Emory both label many of their rates "percent
  of total billed charges" — but Grady also publishes the calculated
  dollar result of that percentage (and it's internally consistent: e.g.
  80% of a $4,149.60 gross charge is exactly the $3,319.68 negotiated
  amount shown), while Emory publishes only the percentage, without the
  gross charge needed to compute an actual number. Same label,
  functionally opposite transparency.
- **CHOA (Arthur M. Blank) is the most transparent file in the dataset**,
  with populated negotiated dollar amounts on every sampled row, and is
  the only hospital that includes a full plain-language explanation of
  its outlier/fee-schedule calculation methodology directly in the file.
- **CHOA's gross charge and discounted cash price are identical on every
  sampled row** — meaning no distinct self-pay/cash discount is actually
  being offered despite the field being populated, worth flagging as a
  transparency gap of a different kind.
- **Wellstar's file mixes billing-adjustment rows with priced-service
  rows.** An initial sample landed entirely on "Reduced Services"
  (CPT modifier 52) line items — real billing codes, but with no
  standalone price data by design, since the modifier only adjusts a
  price defined elsewhere in the file. A second, offset sample was
  needed to reach representative priced services.

## Hospital-Specific Schema Quirks

- **CHOA (Arthur M. Blank)**: column headers use spaces around the pipe
  character for min/max fields (`standard_charge | min`, not
  `standard_charge|min` like other hospitals). Also uses `APR-DRG`
  (All Patient Refined DRG) as its DRG code type, rather than plain
  `DRG`.
- **Grady**: payer+plan rate information is stored as wide, sideways
  column groups (`standard_charge|{payer}|{plan}|negotiated_dollar`,
  etc.) rather than one row per payer. `src/flatten_grady_sample.py`
  discovers payer+plan pairs dynamically from the header rather than
  hardcoding them.
- **Northside**: JSON structure nests payer rates three levels deep
  (service → setting → payer). No `median_amount` equivalent exists in
  this schema.
- **Piedmont**: includes a `LOCAL` code type (hospital-internal codes)
  not mapped to any of the six standard code columns, and is
  intentionally dropped rather than guessed into the wrong field.

## How to Reproduce

1. Install dependencies: `pip install -r requirements.txt --break-system-packages`
2. Sample a hospital's raw file: `python3 src/sample_<hospital>.py`
3. Flatten a sample into the unified schema: `python3 src/flatten_<hospital>_sample.py`
4. Check hospital source URLs are still live: `python3 src/check_sources.py`

## Next Steps

- Build `src/parse_prices.py` / `src/load_database.py` to run the same
  flattening logic against full raw files (not just 25-row samples) and
  load results into the project's SQLite database.
- Expand data-quality metrics to the full files once loaded, to confirm
  whether the sample-based `price_type` breakdowns above hold at scale.
- Integrate CMS hospital quality measures via the Provider Data Catalog
  API for the price-vs-quality analysis.
# Georgia Hospital Price & Quality Explorer

An analysis of how much six major Atlanta-area hospitals charge for
four common medical procedures, and whether higher-priced hospitals
provide measurably better quality of care.

Built using hospitals' federally-mandated machine-readable price
transparency files, combined with CMS hospital quality ratings.

**[View the interactive dashboard →](https://public.tableau.com/views/GeorgiaHospitalPriceQualityExplorer/Dashboard1)**

## The Question

Since 2021, U.S. hospitals have been required to publish their
negotiated prices in a standardized, machine-readable format. In
theory, this makes it possible to compare what different hospitals
charge for the same procedure, and to check whether paying more
actually buys better care.

In practice, six hospitals' files turned out to use three different
data formats, two different labeling conventions for the same billing
codes, and wildly inconsistent price reporting. A meaningful chunk of
this project became about determining whether the data could even
answer the question in the first place, before answering it.

## What This Project Covers

- **6 Atlanta-area hospitals**: Emory University Hospital, Grady
  Memorial Hospital, Northside Hospital Atlanta, Piedmont Atlanta
  Hospital, Wellstar Kennestone Hospital, and Arthur M. Blank Hospital
  (Children's Healthcare of Atlanta)
- **4 procedures**: Head/Brain CT, Knee MRI, Colonoscopy, Cardiac
  Stress Test
- **A Python pipeline** that pulls, parses, and normalizes each
  hospital's differently-structured pricing file into one unified
  database
- **A price-vs-quality comparison** against each hospital's CMS
  quality rating

## Key Findings

- **Median negotiated price for the same procedure varied by up to
  5x across hospitals.** Head CT ranged from $627.65 (Grady) to
  $1,721.85 (CHOA).
- **A hospital's overall CMS star rating did not reliably predict its
  prices.** Among the three hospitals with both reliable price data
  and a standard quality rating, higher star rating predicted higher
  price in only 1 of 4 procedures.
- **A hospital's composite quality score can hide meaningfully
  different performance underneath it.** Grady, the lowest
  overall-rated hospital in this dataset (2 stars), actually
  outperformed two higher-rated hospitals on a specific safety measure
  (43% of measures "better than national average," vs. 12% for both).
- **Identical billing codes don't always mean identical services.**
  The same CPT code can separately bill a hospital's facility fee, a
  physician's interpretation fee, and a technical-equipment fee. Five
  different prices for "the same" service turned out to be three
  legitimately different services sharing one code.
- **Two hospitals label CPT codes as "HCPCS" instead**, meaning a
  naive code search silently missed real data at those hospitals until
  the issue was caught and corrected.

Full methodology, every data-quality issue found and how it was
resolved, and the complete results are documented in
[`data/README.md`](data/README.md), including several cases where an
initial promising-looking pattern didn't hold up under closer
inspection, and is reported as such rather than smoothed over.

## Tech Stack

Python (pandas, requests, ijson) for data extraction and cleaning,
SQLite for storage, SQL for analysis. Six purpose-built parsers handle
three distinct real-world file formats (nested JSON, flat CSV,
wide/pivoted CSV) and one ZIP-wrapped source.

## How to Run This Yourself

```bash
pip install -r requirements.txt --break-system-packages

# Search a hospital's full raw pricing file for a specific procedure code
python3 src/sample_by_code.py "Emory University Hospital" 70450 HCPCS

# Convert that hospital's raw data into the unified schema
python3 src/flatten_emory_sample.py

# Load into the database (use --append to add more procedures without wiping existing data)
python3 src/load_database.py --append

# Pull CMS quality ratings for all six hospitals
python3 src/fetch_cms_quality.py

# Explore the results
sqlite3 data/hospital_prices.db
```

See [`data/README.md`](data/README.md) for the full unified schema,
every hospital-specific quirk encountered, and the saved SQL queries
used to produce the findings above (`sql/median_by_procedure.sql`
and the price-vs-quality queries documented there).

## Project Structure

```
config/       hospital source URLs and metadata
data/
  raw/        full source files (gitignored, regenerate via sample_*.py)
  sample/     targeted excerpts matching searched procedure codes
  processed/  flattened data in the unified schema
sql/          database schema and saved analysis queries
src/          all pipeline scripts (sampling, flattening, loading, CMS fetch)
```
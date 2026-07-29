# georgia-hospital-price-quality
An end-to-end analysis of hospital prices and quality measures across Georgia.

## Retrieval Notes

- Northside Hospital Atlanta's official machine-readable file returned HTTP 403
  to automated Python requests due to CDN access restrictions.
- The file was manually downloaded through a standard web browser and stored
  locally in `data/raw/`.
- The retrieval limitation is logged rather than treated as a missing or
  invalid source.

  ## Raw Data

Raw hospital pricing files are large (50MB–900MB+) and are excluded from
version control via `.gitignore`. To download them locally, run:

    python3 src/download_files.py

Sources and URLs for each hospital are listed in `config/hospitals.csv`.

## Sample Data

`data/sample/` contains small, truncated excerpts of each hospital's raw
file (first ~25 records) so the file structure can be inspected without
downloading the full dataset.

- `northside_sample.json` — Northside Hospital Atlanta, sampled from a
  906MB source file (CMS "tall" JSON format, v3.0.0, retrieved 2026-02-14).
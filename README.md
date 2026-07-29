# georgia-hospital-price-quality
An end-to-end analysis of hospital prices and quality measures across Georgia.

## Retrieval Notes

- Northside Hospital Atlanta's official machine-readable file returned HTTP 403
  to automated Python requests due to CDN access restrictions.
- The file was manually downloaded through a standard web browser and stored
  locally in `data/raw/`.
- The retrieval limitation is logged rather than treated as a missing or
  invalid source.
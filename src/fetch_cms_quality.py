"""
Fetch CMS quality measures for each hospital in this project and load
them into the quality_measures table defined in sql/schema.sql.

Uses the CMS Provider Data Catalog's "Hospital General Information"
dataset (xubh-q36u), which is the same dataset that powers Care
Compare's star ratings. It reports summary-level measure GROUPS
(mortality, safety, readmissions, patient experience, timely/effective
care) rather than every individual granular measure -- a reasonable,
manageable starting point for this project's price-vs-quality analysis.

CCNs (CMS Certification Numbers) were looked up by hand for each
hospital and are NOT derivable from anything else in this project --
hardcoded here, same convention as SOURCE_FORMATS in load_database.py.

IMPORTANT CAVEAT: Arthur M. Blank Hospital (CHOA) is a pediatric
hospital. CMS's standard adult quality reporting program largely
excludes children's hospitals -- expect most or all of its measures to
come back "Not Available". This is a real limitation of the data
source, not a bug in this script.
"""

import sqlite3
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_FILE = PROJECT_ROOT / "data" / "hospital_prices.db"

DATASET_ID = "xubh-q36u"  # Hospital General Information
API_URL = f"https://data.cms.gov/provider-data/api/1/datastore/query/{DATASET_ID}/0"

# Looked up by hand via CMS.gov / Care Compare -- see data/README.md
# for sourcing notes.
HOSPITAL_CCNS = {
    "Emory University Hospital": "110010",
    "Grady Memorial Hospital": "110079",
    "Northside Hospital Atlanta": "110161",
    "Piedmont Atlanta Hospital": "110083",
    "Wellstar Kennestone Hospital": "110035",
    "Arthur M. Blank Hospital": "113300",
}

# Which columns from the CMS dataset to pull in as individual
# quality_measures rows, and what unit label to store for each.
MEASURES_TO_EXTRACT = [
    ("Hospital overall rating", "stars_1_to_5"),
    ("Count of Facility MORT Measures", "measure_count"),
    ("Count of MORT Measures Better", "measure_count"),
    ("Count of MORT Measures Worse", "measure_count"),
    ("Count of Facility Safety Measures", "measure_count"),
    ("Count of Safety Measures Better", "measure_count"),
    ("Count of Safety Measures Worse", "measure_count"),
    ("Count of Facility READM Measures", "measure_count"),
    ("Count of READM Measures Better", "measure_count"),
    ("Count of READM Measures Worse", "measure_count"),
    ("Count of Facility Pt Exp Measures", "measure_count"),
    ("Count of Facility TE Measures", "measure_count"),
]


def to_float(value):
    """CMS uses the literal string 'Not Available' for missing data --
    convert that (and blanks) to None rather than crashing or storing
    it as a fake zero."""
    if value in (None, "", "Not Available"):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def fetch_hospital_record(ccn: str) -> dict:
    """
    Query the CMS datastore API for a single hospital by CCN
    ("Facility ID" in this dataset). Returns the first matching row as
    a dict, or None if no match was found.
    """
    params = {
        "conditions[0][property]": "Facility ID",
        "conditions[0][value]": ccn,
        "conditions[0][operator]": "=",
    }
    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()
    results = response.json()

    if not results:
        return None
    return results[0]


def load_quality_measures(conn: sqlite3.Connection, hospital_id: int,
                            record: dict) -> int:
    """Insert one quality_measures row per extracted metric."""
    rows_inserted = 0

    for column_name, unit in MEASURES_TO_EXTRACT:
        raw_value = record.get(column_name)
        measure_value = to_float(raw_value)

        conn.execute(
            """
            INSERT INTO quality_measures
                (hospital_id, measure_name, measure_value, measure_unit, reporting_period)
            VALUES (?, ?, ?, ?, ?)
            """,
            (hospital_id, column_name, measure_value, unit, None),
        )
        rows_inserted += 1

    return rows_inserted


def get_hospital_ids(conn: sqlite3.Connection) -> dict:
    """Look up each hospital's internal database hospital_id by name."""
    rows = conn.execute("SELECT hospital_id, hospital_name FROM hospitals").fetchall()
    return {name: hospital_id for hospital_id, name in rows}


def main() -> None:
    conn = sqlite3.connect(DB_FILE)

    # Clear any previously-loaded quality measures so this script is
    # safe to re-run.
    conn.execute("DELETE FROM quality_measures")
    conn.commit()

    hospital_ids = get_hospital_ids(conn)

    for hospital_name, ccn in HOSPITAL_CCNS.items():
        hospital_id = hospital_ids.get(hospital_name)
        if hospital_id is None:
            print(f"WARNING: '{hospital_name}' not found in hospitals table "
                  f"-- run load_database.py first. Skipping.")
            continue

        print(f"Fetching quality data for {hospital_name} (CCN {ccn})...")
        record = fetch_hospital_record(ccn)

        if record is None:
            print(f"  No CMS record found for CCN {ccn}.")
            continue

        rows_inserted = load_quality_measures(conn, hospital_id, record)
        conn.commit()

        overall_rating = record.get("Hospital overall rating", "Not Available")
        print(f"  Loaded {rows_inserted} measures. "
              f"Overall star rating: {overall_rating}")

    print("\nDone.")


if __name__ == "__main__":
    main()
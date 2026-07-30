"""
Fetch CMS quality measures for each hospital in this project and load
them into the quality_measures table defined in sql/schema.sql.

UPDATE: the original version tried to filter the CMS datastore API
server-side using query conditions (one request per hospital), but that
endpoint returned a 400 error -- CMS's query syntax for this dataset
wasn't reliably reachable. This version instead downloads the full
national "Hospital General Information" CSV ONCE (confirmed working
directly, no query parameters needed) and filters for our 6 hospitals
locally in Python. Slightly more data transferred (~5,000 hospitals
nationwide), but far more reliable than fighting an undocumented API.

CCNs (CMS Certification Numbers) were looked up by hand for each
hospital and are NOT derivable from anything else in this project.

IMPORTANT CAVEAT: Arthur M. Blank Hospital (CHOA) is a pediatric
hospital. CMS's standard adult quality reporting program largely
excludes children's hospitals -- expect most or all of its measures to
come back "Not Available". This is a real limitation of the data
source, not a bug in this script.
"""

import csv
import io
import sqlite3
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_FILE = PROJECT_ROOT / "data" / "hospital_prices.db"

DATASET_ID = "xubh-q36u"  # Hospital General Information
DOWNLOAD_URL = (
    f"https://data.cms.gov/provider-data/api/1/datastore/query/"
    f"{DATASET_ID}/0/download?format=csv"
)

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

# Reverse lookup: CCN -> hospital_name, used once we're scanning the CSV.
CCN_TO_HOSPITAL = {ccn: name for name, ccn in HOSPITAL_CCNS.items()}

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


def download_and_filter() -> dict:
    """
    Download the full national CSV once and return a dict mapping
    hospital_name -> row (dict), for just our 6 target hospitals.
    """
    print("Downloading CMS Hospital General Information dataset "
          "(nationwide, ~5,000 hospitals)...")

    response = requests.get(DOWNLOAD_URL, timeout=60)
    response.raise_for_status()

    reader = csv.DictReader(io.StringIO(response.text))

    matched_records = {}
    for row in reader:
        facility_id = row.get("Facility ID", "").strip()
        if facility_id in CCN_TO_HOSPITAL:
            hospital_name = CCN_TO_HOSPITAL[facility_id]
            matched_records[hospital_name] = row

    print(f"Matched {len(matched_records)} of {len(HOSPITAL_CCNS)} "
          f"target hospitals.")
    return matched_records


def load_quality_measures(conn: sqlite3.Connection, hospital_id: int,
                            record: dict) -> int:
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
    rows = conn.execute("SELECT hospital_id, hospital_name FROM hospitals").fetchall()
    return {name: hospital_id for hospital_id, name in rows}


def main() -> None:
    conn = sqlite3.connect(DB_FILE)

    conn.execute("DELETE FROM quality_measures")
    conn.commit()

    hospital_ids = get_hospital_ids(conn)
    matched_records = download_and_filter()

    for hospital_name, ccn in HOSPITAL_CCNS.items():
        hospital_id = hospital_ids.get(hospital_name)
        if hospital_id is None:
            print(f"WARNING: '{hospital_name}' not found in hospitals table "
                  f"-- run load_database.py first. Skipping.")
            continue

        record = matched_records.get(hospital_name)
        if record is None:
            print(f"WARNING: CCN {ccn} ({hospital_name}) not found in the "
                  f"CMS dataset. Skipping.")
            continue

        rows_inserted = load_quality_measures(conn, hospital_id, record)
        conn.commit()

        overall_rating = record.get("Hospital overall rating", "Not Available")
        print(f"{hospital_name}: loaded {rows_inserted} measures. "
              f"Overall star rating: {overall_rating}")

    print("\nDone.")


if __name__ == "__main__":
    main()
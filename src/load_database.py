"""
Load all six hospitals' flattened sample data into the SQLite database
defined in sql/schema.sql.

This script is SAFE TO RE-RUN: it clears out existing hospitals/
services/prices data before reloading, so you can tweak a flatten_*.py
script, regenerate a sample, and rerun this without manually cleaning up
old rows first.

What it does, in order:
1. Wipes existing data from prices, services, and hospitals tables
   (children first, to respect foreign key constraints).
2. Reads config/hospitals.csv and inserts one row per hospital into the
   hospitals table, tagging each with the source_format we determined
   by hand while building each hospital's sample/flatten scripts.
3. Reads each data/processed/*_flat.csv file. For each row:
   - Finds or creates the matching service (deduplicated by hospital +
     description + all code fields, since the flattened CSVs repeat
     service-level info on every price row).
   - Inserts one row into prices, referencing that service_id.
"""

import csv
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOSPITALS_FILE = PROJECT_ROOT / "config" / "hospitals.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
SCHEMA_FILE = PROJECT_ROOT / "sql" / "schema.sql"
DB_FILE = PROJECT_ROOT / "data" / "hospital_prices.db"

# Determined by hand while sourcing/sampling each hospital -- not
# something derivable automatically from hospitals.csv.
SOURCE_FORMATS = {
    "Northside Hospital Atlanta": "json",
    "Emory University Hospital": "csv_flat",
    "Grady Memorial Hospital": "csv_wide",
    "Piedmont Atlanta Hospital": "zip_csv",
    "Wellstar Kennestone Hospital": "csv_flat",
    "Arthur M. Blank Hospital": "csv_flat",
}

# Each hospital's flattened sample file.
FLAT_FILES = [
    "northside_sample_flat.csv",
    "emory_sample_flat.csv",
    "grady_sample_flat.csv",
    "piedmont_sample_flat.csv",
    "wellstar_sample_flat.csv",
    "choa_sample_flat.csv",
]

# Columns that make up a service's identity. Two rows with the same
# hospital + all of these values are treated as the SAME service, even
# though the flattened CSVs repeat this info on every price row.
SERVICE_KEY_COLUMNS = [
    "description", "ndc_code", "revenue_code", "cdm_code",
    "hcpcs_code", "cpt_code", "drg_code", "drug_unit", "drug_unit_type",
]


def to_float(value: str):
    """Convert a CSV string to a float, or None if blank/invalid."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def reset_database(conn: sqlite3.Connection) -> None:
    """Ensure the schema exists, then clear existing rows so this script
    can be safely re-run without manually cleaning up first."""
    with open(SCHEMA_FILE, "r") as f:
        conn.executescript(f.read())

    # Delete children before parents to respect foreign key constraints.
    conn.execute("DELETE FROM prices")
    conn.execute("DELETE FROM services")
    conn.execute("DELETE FROM hospitals")
    # Reset autoincrement counters so IDs start fresh each run.
    conn.execute(
        "DELETE FROM sqlite_sequence WHERE name IN "
        "('prices', 'services', 'hospitals')"
    )
    conn.commit()


def load_hospitals(conn: sqlite3.Connection) -> dict:
    """
    Insert one row per hospital from config/hospitals.csv. Returns a dict
    mapping hospital_name -> hospital_id, used when loading services.
    """
    hospital_ids = {}

    with open(HOSPITALS_FILE, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["hospital_name"]
            cursor = conn.execute(
                """
                INSERT INTO hospitals
                    (hospital_name, city, state, source_format, source_url)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    name,
                    row.get("city", ""),
                    row.get("state", ""),
                    SOURCE_FORMATS.get(name, "unknown"),
                    row.get("price_file_url", ""),
                ),
            )
            hospital_ids[name] = cursor.lastrowid

    conn.commit()
    return hospital_ids


def get_or_create_service(conn: sqlite3.Connection, service_cache: dict,
                            hospital_id: int, row: dict) -> int:
    """
    Return the service_id for this row's service, inserting a new
    services row only if this exact (hospital, description, codes)
    combination hasn't been seen yet in this run.
    """
    key = (hospital_id,) + tuple(row.get(col, "") for col in SERVICE_KEY_COLUMNS)

    if key in service_cache:
        return service_cache[key]

    cursor = conn.execute(
        """
        INSERT INTO services
            (hospital_id, description, ndc_code, revenue_code, cdm_code,
             hcpcs_code, cpt_code, drg_code, drug_unit, drug_unit_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hospital_id,
            row.get("description", ""),
            row.get("ndc_code", ""),
            row.get("revenue_code", ""),
            row.get("cdm_code", ""),
            row.get("hcpcs_code", ""),
            row.get("cpt_code", ""),
            row.get("drg_code", ""),
            row.get("drug_unit", ""),
            row.get("drug_unit_type", ""),
        ),
    )
    service_id = cursor.lastrowid
    service_cache[key] = service_id
    return service_id


def load_prices_file(conn: sqlite3.Connection, filepath: Path,
                       hospital_ids: dict, service_cache: dict) -> int:
    """Load one hospital's flattened CSV into services + prices."""
    if not filepath.exists():
        print(f"  Skipping {filepath.name} -- file not found.")
        return 0

    rows_loaded = 0

    with open(filepath, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hospital_name = row.get("hospital_name", "")
            hospital_id = hospital_ids.get(hospital_name)

            if hospital_id is None:
                print(
                    f"  WARNING: '{hospital_name}' in {filepath.name} "
                    f"doesn't match any hospital in hospitals.csv -- "
                    f"skipping this row."
                )
                continue

            service_id = get_or_create_service(
                conn, service_cache, hospital_id, row
            )

            conn.execute(
                """
                INSERT INTO prices
                    (service_id, setting, gross_charge, discounted_cash,
                     minimum_charge, maximum_charge, payer_name, plan_name,
                     negotiated_price, negotiated_percentage, median_amount,
                     price_type, resolved_price, methodology)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    service_id,
                    row.get("setting", ""),
                    to_float(row.get("gross_charge")),
                    to_float(row.get("discounted_cash")),
                    to_float(row.get("minimum_charge")),
                    to_float(row.get("maximum_charge")),
                    row.get("payer_name", ""),
                    row.get("plan_name", ""),
                    to_float(row.get("negotiated_price")),
                    to_float(row.get("negotiated_percentage")),
                    to_float(row.get("median_amount")),
                    row.get("price_type", ""),
                    to_float(row.get("resolved_price")),
                    row.get("methodology", ""),
                ),
            )
            rows_loaded += 1

    conn.commit()
    return rows_loaded


def main() -> None:
    conn = sqlite3.connect(DB_FILE)

    print("Resetting database (schema + clearing old rows)...")
    reset_database(conn)

    print("Loading hospitals...")
    hospital_ids = load_hospitals(conn)
    print(f"  Loaded {len(hospital_ids)} hospitals.")

    service_cache = {}
    total_price_rows = 0

    print("Loading services + prices from each hospital's flattened CSV...")
    for filename in FLAT_FILES:
        filepath = PROCESSED_DIR / filename
        rows_loaded = load_prices_file(conn, filepath, hospital_ids, service_cache)
        print(f"  {filename}: {rows_loaded} price rows loaded.")
        total_price_rows += rows_loaded

    print(f"\nDone. {len(hospital_ids)} hospitals, "
          f"{len(service_cache)} unique services, "
          f"{total_price_rows} price rows.")

    conn.close()


if __name__ == "__main__":
    main()
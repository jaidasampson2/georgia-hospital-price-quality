"""
Load hospitals' flattened data into the SQLite database defined in
sql/schema.sql.

UPDATE: added --append mode. Previously this script always wiped the
database before reloading -- fine while iterating on one procedure's
sample data, but a problem now that we're searching for MULTIPLE
procedures one at a time (each search overwrites the same hospital
sample files). Without --append, loading Knee MRI data after Head CT
data would DELETE the Head CT rows first, losing the earlier procedure
instead of accumulating a full multi-procedure dataset.

Usage:
    python3 src/load_database.py            # full reset (default, same as before)
    python3 src/load_database.py --append    # add this run's data without wiping existing rows
"""

import argparse
import csv
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOSPITALS_FILE = PROJECT_ROOT / "config" / "hospitals.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
SCHEMA_FILE = PROJECT_ROOT / "sql" / "schema.sql"
DB_FILE = PROJECT_ROOT / "data" / "hospital_prices.db"

SOURCE_FORMATS = {
    "Northside Hospital Atlanta": "json",
    "Emory University Hospital": "csv_flat",
    "Grady Memorial Hospital": "csv_wide",
    "Piedmont Atlanta Hospital": "zip_csv",
    "Wellstar Kennestone Hospital": "csv_flat",
    "Arthur M. Blank Hospital": "csv_flat",
}

FLAT_FILES = [
    "northside_sample_flat.csv",
    "emory_sample_flat.csv",
    "grady_sample_flat.csv",
    "piedmont_sample_flat.csv",
    "wellstar_sample_flat.csv",
    "choa_sample_flat.csv",
]

SERVICE_KEY_COLUMNS = [
    "description", "ndc_code", "revenue_code", "cdm_code",
    "hcpcs_code", "cpt_code", "drg_code", "drug_unit", "drug_unit_type",
    "billing_class", "modifiers",
]


def to_float(value: str):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Make sure tables exist. Safe to call every time -- CREATE TABLE
    IF NOT EXISTS does nothing if they're already there."""
    with open(SCHEMA_FILE, "r") as f:
        conn.executescript(f.read())
    conn.commit()


def wipe_database(conn: sqlite3.Connection) -> None:
    """Full reset: delete all existing rows. Only used when --append is
    NOT passed."""
    conn.execute("DELETE FROM prices")
    conn.execute("DELETE FROM services")
    conn.execute("DELETE FROM hospitals")
    conn.execute(
        "DELETE FROM sqlite_sequence WHERE name IN "
        "('prices', 'services', 'hospitals')"
    )
    conn.commit()


def load_hospitals(conn: sqlite3.Connection, append: bool) -> dict:
    """
    In non-append mode: insert all hospitals fresh (table was just
    wiped). In append mode: reuse existing hospital rows if they're
    already there, only inserting hospitals that are genuinely new.
    """
    hospital_ids = {}

    if append:
        existing = conn.execute(
            "SELECT hospital_id, hospital_name FROM hospitals"
        ).fetchall()
        for hospital_id, name in existing:
            hospital_ids[name] = hospital_id

    with open(HOSPITALS_FILE, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["hospital_name"]

            if append and name in hospital_ids:
                # Already in the database from an earlier run -- reuse it.
                continue

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


def load_existing_services(conn: sqlite3.Connection) -> dict:
    """
    In append mode, seed the service_cache with services already in the
    database, so a procedure search that happens to re-match a service
    from an earlier run reuses the same service_id instead of creating
    a duplicate row.
    """
    service_cache = {}
    rows = conn.execute(
        """
        SELECT service_id, hospital_id, description, ndc_code, revenue_code,
               cdm_code, hcpcs_code, cpt_code, drg_code, drug_unit,
               drug_unit_type, billing_class, modifiers
        FROM services
        """
    ).fetchall()

    for row in rows:
        service_id = row[0]
        key = tuple(v if v is not None else "" for v in row[1:])
        service_cache[key] = service_id

    return service_cache


def get_or_create_service(conn: sqlite3.Connection, service_cache: dict,
                            hospital_id: int, row: dict) -> int:
    key = (hospital_id,) + tuple(row.get(col, "") for col in SERVICE_KEY_COLUMNS)

    if key in service_cache:
        return service_cache[key]

    cursor = conn.execute(
        """
        INSERT INTO services
            (hospital_id, description, ndc_code, revenue_code, cdm_code,
             hcpcs_code, cpt_code, drg_code, drug_unit, drug_unit_type,
             billing_class, modifiers)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            row.get("billing_class", ""),
            row.get("modifiers", ""),
        ),
    )
    service_id = cursor.lastrowid
    service_cache[key] = service_id
    return service_id


def load_prices_file(conn: sqlite3.Connection, filepath: Path,
                       hospital_ids: dict, service_cache: dict) -> int:
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
    parser = argparse.ArgumentParser(
        description="Load flattened hospital CSVs into the SQLite database."
    )
    parser.add_argument(
        "--append", action="store_true",
        help="Add this run's data without wiping existing rows first."
    )
    args = parser.parse_args()

    conn = sqlite3.connect(DB_FILE)

    ensure_schema(conn)

    if args.append:
        print("Running in --append mode: existing data will NOT be wiped.")
    else:
        print("Resetting database (wiping existing rows)...")
        wipe_database(conn)

    print("Loading hospitals...")
    hospital_ids = load_hospitals(conn, append=args.append)
    print(f"  {len(hospital_ids)} hospitals in database.")

    service_cache = load_existing_services(conn) if args.append else {}
    if args.append:
        print(f"  Seeded cache with {len(service_cache)} existing services.")

    total_price_rows = 0

    print("Loading services + prices from each hospital's flattened CSV...")
    for filename in FLAT_FILES:
        filepath = PROCESSED_DIR / filename
        rows_loaded = load_prices_file(conn, filepath, hospital_ids, service_cache)
        print(f"  {filename}: {rows_loaded} price rows loaded.")
        total_price_rows += rows_loaded

    total_services = conn.execute("SELECT COUNT(*) FROM services").fetchone()[0]
    total_prices_in_db = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]

    print(f"\nThis run added {total_price_rows} price rows.")
    print(f"Database now contains: {len(hospital_ids)} hospitals, "
          f"{total_services} unique services, {total_prices_in_db} total price rows.")

    conn.close()


if __name__ == "__main__":
    main()
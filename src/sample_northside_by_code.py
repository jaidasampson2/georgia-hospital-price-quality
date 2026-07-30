"""
Search Northside's FULL 906MB raw JSON file for service records matching
a specific billing code, instead of grabbing the first N records.

Same motivation as sample_by_code.py (the CSV version): a random sample
of Northside's services didn't overlap with any other hospital's random
sample. This streams through the ENTIRE file using ijson (never loading
it fully into memory) and keeps only services whose code_information
list contains a matching code + type.

IMPORTANT: this OVERWRITES data/sample/northside_sample.json.

Usage:
    python3 src/sample_northside_by_code.py 70450 CPT
"""

import argparse
import json
from decimal import Decimal
from pathlib import Path

import ijson

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "581954432-1457396079_northside-hospital-inc_standardcharges.json"
SAMPLE_FILE = PROJECT_ROOT / "data" / "sample" / "northside_sample.json"

MAX_MATCHES = 200


def service_matches_code(service: dict, target_code: str, code_type: str) -> bool:
    for code_entry in service.get("code_information", []) or []:
        if (str(code_entry.get("code", "")) == target_code
                and str(code_entry.get("type", "")).upper() == code_type.upper()):
            return True
    return False


def get_metadata() -> dict:
    """Grab the top-level hospital metadata fields, same approach as
    the original sample_data.py exploration script."""
    metadata = {}
    with open(RAW_FILE, "rb") as f:
        for prefix, event, value in ijson.parse(f):
            if prefix == "standard_charge_information" and event == "start_array":
                break
            if event in ("string", "number", "boolean", "null"):
                if "." not in prefix and prefix != "":
                    metadata[prefix] = value
    return metadata


def convert_decimals(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def search_for_code(target_code: str, code_type: str) -> None:
    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Could not find the raw Northside file at: {RAW_FILE}\n"
            f"This script needs the full 906MB raw file (manually "
            f"downloaded earlier), not the small sample."
        )

    print(f"Searching Northside's full raw file for code {target_code} "
          f"(type {code_type})...")
    print("This streams through the entire 906MB file -- it may take a "
          "few minutes.")

    metadata = get_metadata()

    matched_services = []
    services_scanned = 0

    with open(RAW_FILE, "rb") as f:
        items = ijson.items(f, "standard_charge_information.item")
        for service in items:
            services_scanned += 1

            if service_matches_code(service, target_code, code_type):
                matched_services.append(service)
                if len(matched_services) >= MAX_MATCHES:
                    print(f"  Hit MAX_MATCHES cap ({MAX_MATCHES}) -- stopping early.")
                    break

            if services_scanned % 50000 == 0:
                print(f"  ...scanned {services_scanned} services so far, "
                      f"{len(matched_services)} matches found.")

    sample = {**metadata, "standard_charge_information": matched_services}

    SAMPLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SAMPLE_FILE, "w") as f:
        json.dump(sample, f, indent=2, default=convert_decimals)

    print(f"Scanned {services_scanned} total service records.")
    print(f"Found {len(matched_services)} matching services.")
    print(f"Wrote sample to {SAMPLE_FILE}")

    if len(matched_services) == 0:
        print(
            f"  NOTE: no matches found for code {target_code}. Northside "
            f"may not offer this procedure, or may use a different code."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search Northside's full raw JSON for services matching a billing code."
    )
    parser.add_argument("target_code", help="The billing code to search for, e.g. 70450")
    parser.add_argument("code_type", help="Code type, e.g. CPT or HCPCS")
    args = parser.parse_args()

    search_for_code(args.target_code, args.code_type)


if __name__ == "__main__":
    main()
"""
Diagnostic: count how many times each code TYPE (CPT, HCPCS, NDC, RC,
CDM, DRG, etc.) actually appears across a hospital's FULL raw CSV file.

This answers a more fundamental question than searching for one code at
a time: does this hospital's file substantively use CPT codes at all,
or did we just happen to pick 4 procedures it doesn't offer?

Usage:
    python3 src/count_code_types.py "Emory University Hospital"
"""

import argparse
import csv
import io
from collections import Counter
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOSPITALS_FILE = PROJECT_ROOT / "config" / "hospitals.csv"

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
}


def get_hospital_url(hospital_name: str) -> str:
    hospitals = pd.read_csv(HOSPITALS_FILE)
    match = hospitals[hospitals["hospital_name"] == hospital_name]
    if match.empty:
        raise ValueError(f"Could not find '{hospital_name}' in {HOSPITALS_FILE}")
    return match.iloc[0]["price_file_url"]


def parse_first_cell(line: str) -> str:
    reader = csv.reader(io.StringIO(line))
    row = next(reader, [])
    return row[0].strip().lower() if row else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("hospital_name")
    args = parser.parse_args()

    url = get_hospital_url(args.hospital_name)
    print(f"Scanning {args.hospital_name}'s full file for code type frequency...")

    response = requests.get(url, headers=HTTP_HEADERS, stream=True, timeout=60)
    response.raise_for_status()

    header_line = None
    header_list = None
    type_counts = Counter()
    lines_scanned = 0

    for line in response.iter_lines(decode_unicode=True):
        if line is None:
            continue
        lines_scanned += 1

        if header_line is None:
            if parse_first_cell(line) == "description":
                header_line = line
                header_list = next(csv.reader(io.StringIO(line)))
            continue

        reader = csv.reader(io.StringIO(line))
        values = next(reader, [])
        if len(values) != len(header_list):
            continue
        row = dict(zip(header_list, values))

        for slot in range(1, 5):
            code_type = row.get(f"code|{slot}|type", "")
            if code_type:
                type_counts[code_type] += 1

        if lines_scanned % 200000 == 0:
            print(f"  ...scanned {lines_scanned} lines so far.")

    response.close()

    print(f"\nScanned {lines_scanned} total lines.")
    print("Code type frequency across the full file:")
    for code_type, count in type_counts.most_common():
        print(f"  {code_type}: {count}")


if __name__ == "__main__":
    main()
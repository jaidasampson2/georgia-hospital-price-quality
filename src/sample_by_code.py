"""
Search a CSV-based hospital's FULL raw pricing file for rows matching a
specific billing code (e.g. a CPT code for a target procedure), instead
of just grabbing the first N rows.

Why this exists: random small samples from each hospital landed on
completely different, non-overlapping services (drugs, room types,
surgical supplies, DRG charges) -- meaningless for cross-hospital price
comparison. This script instead streams through the ENTIRE raw file
(never loading it fully into memory) and keeps only rows whose code|1
through code|4 columns match the target code and code type, so we end
up with genuinely comparable data across hospitals.

Works for all CSV-based hospitals in this project: Emory, Grady (wide
format -- but its code columns are structured the same as the others,
unaffected by its payer-plan pivoting), Piedmont (ZIP-wrapped), and
Wellstar. CHOA needs special handling for "APR-DRG" as noted in its
flattener, but standard CPT/HCPCS codes work the same way here.

IMPORTANT: this OVERWRITES the hospital's existing data/sample/*.csv
file. That's intentional -- once you're searching for specific
procedures, a random 25-row sample no longer serves a purpose; a
targeted, code-matched sample is strictly more useful and plugs into
the exact same flatten_*.py scripts you already have.

Usage:
    python3 src/sample_by_code.py "Emory University Hospital" 70450 CPT
    python3 src/sample_by_code.py "Grady Memorial Hospital" 73721 CPT
"""

import argparse
import csv
import io
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOSPITALS_FILE = PROJECT_ROOT / "config" / "hospitals.csv"

# Same source_format mapping used in load_database.py -- kept here too
# since this script needs to know upfront whether to expect a plain CSV
# or a ZIP-wrapped one.
SOURCE_FORMATS = {
    "Emory University Hospital": "csv_flat",
    "Grady Memorial Hospital": "csv_wide",
    "Piedmont Atlanta Hospital": "zip_csv",
    "Wellstar Kennestone Hospital": "csv_flat",
    "Arthur M. Blank Hospital": "csv_flat",
}

# Maps each hospital to the sample file its flatten_*.py script expects.
HOSPITAL_TO_SAMPLE_FILE = {
    "Emory University Hospital": "emory_sample.csv",
    "Grady Memorial Hospital": "grady_sample.csv",
    "Piedmont Atlanta Hospital": "piedmont_sample.csv",
    "Wellstar Kennestone Hospital": "wellstar_sample.csv",
    "Arthur M. Blank Hospital": "choa_sample.csv",
}

MAX_MATCHES = 200  # safety cap in case a code matches an unexpectedly large number of rows

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


def row_matches_code(header: list, line: str, target_code: str, code_type: str) -> bool:
    """
    Parse one data line into its column values and check whether any of
    its code|1..4 / code|1|type..4|type pairs match the target code and
    type.
    """
    reader = csv.reader(io.StringIO(line))
    values = next(reader, [])
    if len(values) != len(header):
        # Malformed row (unlikely, but real-world files can have these) --
        # skip rather than crash.
        return False

    row = dict(zip(header, values))
    for slot in range(1, 5):
        code_value = row.get(f"code|{slot}", "")
        this_code_type = row.get(f"code|{slot}|type", "")
        if code_value == target_code and this_code_type.upper() == code_type.upper():
            return True
    return False


def open_csv_stream(url: str, source_format: str):
    """
    Return an iterator of text lines for the hospital's CSV data,
    regardless of whether it's a plain CSV (stream directly) or a
    ZIP-wrapped CSV (download fully to temp, then read from inside it).
    Also returns a cleanup function to call when done.
    """
    if source_format == "zip_csv":
        temp_zip = Path(tempfile.gettempdir()) / "hospital_code_search_temp.zip"
        print("Downloading ZIP file (unavoidable for ZIP-wrapped hospitals)...")
        with requests.get(url, headers=HTTP_HEADERS, stream=True, timeout=60) as response:
            response.raise_for_status()
            with open(temp_zip, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)

        zip_file = zipfile.ZipFile(temp_zip, "r")
        csv_entries = [n for n in zip_file.namelist() if n.lower().endswith(".csv")]
        if not csv_entries:
            raise ValueError("No CSV file found inside the ZIP archive.")
        raw_bytes = zip_file.open(csv_entries[0])
        text_stream = io.TextIOWrapper(raw_bytes, encoding="utf-8")

        def cleanup():
            text_stream.close()
            zip_file.close()
            if temp_zip.exists():
                temp_zip.unlink()

        return (line.rstrip("\n").rstrip("\r") for line in text_stream), cleanup

    else:
        response = requests.get(url, headers=HTTP_HEADERS, stream=True, timeout=60)
        response.raise_for_status()

        def cleanup():
            response.close()

        return response.iter_lines(decode_unicode=True), cleanup


def search_for_code(hospital_name: str, target_code: str, code_type: str) -> None:
    url = get_hospital_url(hospital_name)
    source_format = SOURCE_FORMATS.get(hospital_name)
    output_filename = HOSPITAL_TO_SAMPLE_FILE.get(hospital_name)

    if not source_format or not output_filename:
        raise ValueError(
            f"'{hospital_name}' isn't a recognized CSV-based hospital in "
            f"this script. (Northside uses sample_northside_by_code.py instead.)"
        )

    output_file = PROJECT_ROOT / "data" / "sample" / output_filename

    print(f"Searching {hospital_name} for code {target_code} (type {code_type})...")

    lines, cleanup = open_csv_stream(url, source_format)

    header_line = None
    header_list = None
    matched_lines = []
    lines_scanned = 0

    try:
        for line in lines:
            if line is None:
                continue
            lines_scanned += 1

            if header_line is None:
                if parse_first_cell(line) == "description":
                    header_line = line
                    header_list = next(csv.reader(io.StringIO(line)))
                elif lines_scanned >= 20:
                    raise RuntimeError(
                        "Could not find a header row starting with "
                        "'description' within the first 20 lines."
                    )
                continue

            if row_matches_code(header_list, line, target_code, code_type):
                matched_lines.append(line)
                if len(matched_lines) >= MAX_MATCHES:
                    print(f"  Hit MAX_MATCHES cap ({MAX_MATCHES}) -- stopping early.")
                    break

            if lines_scanned % 200000 == 0:
                print(f"  ...scanned {lines_scanned} lines so far, "
                      f"{len(matched_lines)} matches found.")
    finally:
        cleanup()

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", newline="") as f:
        f.write(header_line + "\n")
        for line in matched_lines:
            f.write(line + "\n")

    print(f"Scanned {lines_scanned} total lines.")
    print(f"Found {len(matched_lines)} matching rows.")
    print(f"Wrote header + {len(matched_lines)} rows to {output_file}")

    if len(matched_lines) == 0:
        print(
            f"  NOTE: no matches found for code {target_code}. This hospital "
            f"may not offer this procedure, or may use a different code for it."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search a hospital's full raw CSV for rows matching a billing code."
    )
    parser.add_argument("hospital_name", help="Exact hospital_name from config/hospitals.csv")
    parser.add_argument("target_code", help="The billing code to search for, e.g. 70450")
    parser.add_argument("code_type", help="Code type, e.g. CPT or HCPCS")
    args = parser.parse_args()

    search_for_code(args.hospital_name, args.target_code, args.code_type)


if __name__ == "__main__":
    main()
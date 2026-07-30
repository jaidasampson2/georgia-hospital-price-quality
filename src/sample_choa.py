"""
Create a small sample of Arthur M. Blank Hospital's (Children's
Healthcare of Atlanta) pricing CSV without downloading or loading the
full file into memory.

This is your 6th and final hospital. Adapted directly from
sample_wellstar.py -- same plain-CSV streaming approach, same
header-detection logic, plus the SKIP_ROWS option in case the first
block of rows here also turns out to be unrepresentative (as happened
with Wellstar's modifier-code rows).
"""

import csv
import io
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOSPITALS_FILE = PROJECT_ROOT / "config" / "hospitals.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "sample" / "choa_sample.csv"

HOSPITAL_NAME = "Arthur M. Blank Hospital"

# Start at 0 -- only bump this up later if the first sample turns out to
# be unrepresentative, same as we did for Wellstar.
SKIP_ROWS = 0
N_DATA_ROWS = 25

MAX_LINES_TO_SCAN_FOR_HEADER = 20


def get_hospital_url() -> str:
    """Look up CHOA's price_file_url from config/hospitals.csv."""
    hospitals = pd.read_csv(HOSPITALS_FILE)

    match = hospitals[hospitals["hospital_name"] == HOSPITAL_NAME]
    if match.empty:
        raise ValueError(
            f"Could not find a row for '{HOSPITAL_NAME}' in {HOSPITALS_FILE}"
        )

    return match.iloc[0]["price_file_url"]


def parse_first_cell(line: str) -> str:
    """Same helper used across the other sample_*.py scripts."""
    reader = csv.reader(io.StringIO(line))
    row = next(reader, [])
    return row[0].strip().lower() if row else ""


def stream_sample(url: str) -> None:
    """
    Stream lines from the CSV URL. Skip metadata lines until we find the
    real header row, then optionally skip SKIP_ROWS more data rows, then
    collect the next N_DATA_ROWS rows as our sample.
    """
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/149.0.0.0 Safari/537.36"
        ),
    }

    header_line = None
    rows_skipped = 0
    data_lines = []
    lines_scanned = 0

    with requests.get(url, headers=headers, stream=True, timeout=30) as response:
        response.raise_for_status()

        for line in response.iter_lines(decode_unicode=True):
            if line is None:
                continue

            lines_scanned += 1

            if header_line is None:
                if parse_first_cell(line) == "description":
                    header_line = line
                elif lines_scanned >= MAX_LINES_TO_SCAN_FOR_HEADER:
                    raise RuntimeError(
                        f"Could not find a header row starting with "
                        f"'description' within the first "
                        f"{MAX_LINES_TO_SCAN_FOR_HEADER} lines."
                    )
                continue

            if rows_skipped < SKIP_ROWS:
                rows_skipped += 1
                continue

            data_lines.append(line)

            if len(data_lines) >= N_DATA_ROWS:
                break

    with open(OUTPUT_FILE, "w", newline="") as f:
        f.write(header_line + "\n")
        for line in data_lines:
            f.write(line + "\n")

    print(f"Scanned {lines_scanned} lines total.")
    print(f"Skipped {rows_skipped} data rows before starting to sample.")
    print(f"Wrote 1 header row + {len(data_lines)} data rows to {OUTPUT_FILE}")


def main() -> None:
    url = get_hospital_url()
    print(f"Streaming sample from: {url}")
    stream_sample(url)


if __name__ == "__main__":
    main()
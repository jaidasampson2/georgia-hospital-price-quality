"""
Create a small sample of Grady Memorial Hospital's pricing CSV without
downloading or loading the full ~183 MB file into memory.

This script is adapted directly from sample_emory.py. The header-detection
logic (scan for the row whose first cell is "description") is left
unchanged and generic on purpose -- we don't yet know whether Grady uses
the same 2-row metadata block Emory did, or a different number of rows,
or possibly none at all. Rather than guessing, the script will find
Grady's real header wherever it happens to be.
"""

import csv
import io
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOSPITALS_FILE = PROJECT_ROOT / "config" / "hospitals.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "sample" / "grady_sample.csv"

HOSPITAL_NAME = "Grady Memorial Hospital"

N_DATA_ROWS = 25

MAX_LINES_TO_SCAN_FOR_HEADER = 20


def get_hospital_url() -> str:
    """Look up Grady's price_file_url from config/hospitals.csv."""
    hospitals = pd.read_csv(HOSPITALS_FILE)

    match = hospitals[hospitals["hospital_name"] == HOSPITAL_NAME]
    if match.empty:
        raise ValueError(
            f"Could not find a row for '{HOSPITAL_NAME}' in {HOSPITALS_FILE}"
        )

    return match.iloc[0]["price_file_url"]


def parse_first_cell(line: str) -> str:
    """
    Safely read just the first column of a CSV line, using the csv module
    so quoted commas inside a field don't break the parsing.
    """
    reader = csv.reader(io.StringIO(line))
    row = next(reader, [])
    return row[0].strip().lower() if row else ""


def stream_sample(url: str) -> None:
    """
    Stream lines from the CSV URL. Skip metadata lines until we find the
    real header row (first cell == "description"), then collect that
    header plus the next N_DATA_ROWS data lines. Stop reading as soon as
    we have what we need.
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
                        f"{MAX_LINES_TO_SCAN_FOR_HEADER} lines. This "
                        f"hospital's file may use a different layout."
                    )
                continue

            data_lines.append(line)

            if len(data_lines) >= N_DATA_ROWS:
                break

    with open(OUTPUT_FILE, "w", newline="") as f:
        f.write(header_line + "\n")
        for line in data_lines:
            f.write(line + "\n")

    print(f"Scanned {lines_scanned} lines to locate the header row.")
    print(f"Wrote 1 header row + {len(data_lines)} data rows to {OUTPUT_FILE}")


def main() -> None:
    url = get_hospital_url()
    print(f"Streaming sample from: {url}")
    stream_sample(url)


if __name__ == "__main__":
    main()
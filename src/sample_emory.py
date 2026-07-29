"""
Create a small sample of Emory University Hospital's pricing CSV without
downloading or loading the full ~54 MB file into memory.

Why we detect the header row instead of assuming it's line 1:
CMS "wide" template CSVs (like Emory's) put a 2-row hospital metadata
block BEFORE the real column headers:
    Row 1: hospital-level column names (hospital_name, last_updated_on, ...)
    Row 2: hospital-level values (one row describing the hospital itself)
    Row 3: the REAL column headers for service/price data (description,
           code|1, setting, payer_name, standard_charge|gross, ...)
    Row 4+: actual service/price data rows

Rather than hardcoding "skip 2 rows" -- which might not hold for every
hospital's file -- this script scans incoming lines and looks for the
row whose first column is literally "description". That's the row CMS
requires every hospital to use as the real header for its service-level
data, so detecting it this way should generalize to other hospital CSVs
later, even if they have a different number of metadata rows above it.
"""

import csv
import io
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOSPITALS_FILE = PROJECT_ROOT / "config" / "hospitals.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "sample" / "emory_sample.csv"

HOSPITAL_NAME = "Emory University Hospital"

N_DATA_ROWS = 25

# Safety limit: how many lines we're willing to read while searching for
# the real header, in case something unexpected happens and "description"
# never appears (we don't want to accidentally stream the whole 54 MB file).
MAX_LINES_TO_SCAN_FOR_HEADER = 20


def get_emory_url() -> str:
    """Look up Emory's price_file_url from config/hospitals.csv."""
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
    so quoted commas inside a field don't break the parsing (this matters
    for Emory's file, since some cells contain long comma-filled text).
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
                # Still searching for the real header row.
                if parse_first_cell(line) == "description":
                    header_line = line
                elif lines_scanned >= MAX_LINES_TO_SCAN_FOR_HEADER:
                    raise RuntimeError(
                        f"Could not find a header row starting with "
                        f"'description' within the first "
                        f"{MAX_LINES_TO_SCAN_FOR_HEADER} lines. This "
                        f"hospital's file may use a different layout."
                    )
                # Either way, metadata lines before the header are not
                # written to the output -- we only want the real header
                # and the service/price data rows.
                continue

            # We already found the header -- now we're collecting data rows.
            data_lines.append(line)

            if len(data_lines) >= N_DATA_ROWS:
                # Got everything we need. Breaking here, inside the
                # streamed "with" block, closes the connection without
                # downloading the rest of the ~54 MB file.
                break

    with open(OUTPUT_FILE, "w", newline="") as f:
        f.write(header_line + "\n")
        for line in data_lines:
            f.write(line + "\n")

    print(f"Scanned {lines_scanned} lines to locate the header row.")
    print(f"Wrote 1 header row + {len(data_lines)} data rows to {OUTPUT_FILE}")


def main() -> None:
    url = get_emory_url()
    print(f"Streaming sample from: {url}")
    stream_sample(url)


if __name__ == "__main__":
    main()
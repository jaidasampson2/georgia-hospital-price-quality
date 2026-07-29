"""
Create a small sample of Piedmont Atlanta Hospital's pricing CSV, which
is distributed as a ~75 MB ZIP file rather than a plain CSV.

Why this script downloads the full ZIP (unlike our other sample_*.py
scripts, which stream and stop early):
ZIP files store their table of contents (the "central directory") at the
END of the file, not the beginning. To know which file is inside the ZIP
and where it starts, a reader technically needs to see the end of the
file first. It IS possible to fetch just the central directory using
HTTP range requests, but that adds real complexity for a one-time
sampling script. Since Piedmont's ZIP is ~75 MB (not 900 MB like
Northside), a full download is a reasonable, simple tradeoff here --
it happens once, into a temporary location, and is deleted immediately
after we extract our small sample.

Once the ZIP is downloaded and the CSV is extracted, this script reuses
the exact same header-detection logic as sample_emory.py and
sample_grady.py -- scan for the row whose first cell is "description",
then keep the next N_DATA_ROWS rows.
"""

import csv
import io
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOSPITALS_FILE = PROJECT_ROOT / "config" / "hospitals.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "sample" / "piedmont_sample.csv"

HOSPITAL_NAME = "Piedmont Atlanta Hospital"

N_DATA_ROWS = 25
MAX_LINES_TO_SCAN_FOR_HEADER = 20


def get_hospital_url() -> str:
    """Look up Piedmont's price_file_url from config/hospitals.csv."""
    hospitals = pd.read_csv(HOSPITALS_FILE)

    match = hospitals[hospitals["hospital_name"] == HOSPITAL_NAME]
    if match.empty:
        raise ValueError(
            f"Could not find a row for '{HOSPITAL_NAME}' in {HOSPITALS_FILE}"
        )

    return match.iloc[0]["price_file_url"]


def download_zip_to_temp(url: str) -> Path:
    """Download the ZIP file to a temporary location on disk."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/149.0.0.0 Safari/537.36"
        ),
    }

    temp_zip = Path(tempfile.gettempdir()) / "piedmont_download_temp.zip"

    print("Downloading ZIP file (this is the one slow step -- ~75 MB)...")
    with requests.get(url, headers=headers, stream=True, timeout=60) as response:
        response.raise_for_status()
        with open(temp_zip, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)

    print(f"Downloaded to temporary file: {temp_zip}")
    return temp_zip


def find_csv_entry(zip_file: zipfile.ZipFile) -> str:
    """
    Find the CSV file inside the ZIP archive. Piedmont's ZIP is expected
    to contain exactly one relevant standard charges CSV, but we search
    rather than assume a specific filename in case that changes.
    """
    csv_entries = [
        name for name in zip_file.namelist() if name.lower().endswith(".csv")
    ]

    if not csv_entries:
        raise ValueError("No CSV file found inside the ZIP archive.")

    if len(csv_entries) > 1:
        print(
            f"Warning: found {len(csv_entries)} CSV files in the ZIP, "
            f"using the first one: {csv_entries[0]}"
        )

    return csv_entries[0]


def parse_first_cell(line: str) -> str:
    """Same helper used in sample_emory.py / sample_grady.py."""
    reader = csv.reader(io.StringIO(line))
    row = next(reader, [])
    return row[0].strip().lower() if row else ""


def sample_csv_from_zip(zip_path: Path) -> None:
    """
    Open the CSV entry inside the ZIP and apply the same header-detection
    + N-data-rows sampling logic used for our other CSV-based hospitals.
    """
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zip_file:
        csv_entry_name = find_csv_entry(zip_file)
        print(f"Reading CSV entry from ZIP: {csv_entry_name}")

        with zip_file.open(csv_entry_name) as raw_bytes:
            # ZIP entries are opened as raw bytes -- wrap in a text
            # decoder so we can read it line by line like a normal file.
            text_stream = io.TextIOWrapper(raw_bytes, encoding="utf-8")

            header_line = None
            data_lines = []
            lines_scanned = 0

            for line in text_stream:
                line = line.rstrip("\n").rstrip("\r")
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
    print(f"Fetching ZIP from: {url}")

    temp_zip = download_zip_to_temp(url)

    try:
        sample_csv_from_zip(temp_zip)
    finally:
        # Clean up the ~75 MB temporary download regardless of whether
        # sampling succeeded or failed -- we never want this large file
        # lingering outside data/raw/.
        if temp_zip.exists():
            temp_zip.unlink()
            print("Removed temporary ZIP download.")


if __name__ == "__main__":
    main()
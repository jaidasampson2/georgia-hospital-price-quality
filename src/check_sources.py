from pathlib import Path

import pandas as pd
import requests


# Locate the project folder regardless of where the script is run from.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOSPITALS_FILE = PROJECT_ROOT / "config" / "hospitals.csv"


def check_url(hospital_name: str, url: str) -> None:
    """Check whether a hospital pricing URL is reachable."""

    if pd.isna(url) or not str(url).strip():
        print(f"SKIPPED: {hospital_name} has no pricing URL.")
        return

    try:
        # stream=True prevents the entire large pricing file from downloading.
        with requests.get(
            str(url).strip(),
            stream=True,
            timeout=30,
            allow_redirects=True,
        ) as response:
            status = response.status_code
            content_type = response.headers.get("Content-Type", "Unknown")
            content_length = response.headers.get("Content-Length", "Unknown")

            if response.ok:
                print(f"SUCCESS: {hospital_name}")
            else:
                print(f"FAILED: {hospital_name}")

            print(f"  Status code: {status}")
            print(f"  Content type: {content_type}")
            print(f"  File size in bytes: {content_length}")
            print(f"  Final URL: {response.url}")

    except requests.RequestException as error:
        print(f"ERROR: {hospital_name}")
        print(f"  {error}")


def main() -> None:
    """Load the hospital configuration file and check available URLs."""

    if not HOSPITALS_FILE.exists():
        raise FileNotFoundError(
            f"Could not find the hospital file at: {HOSPITALS_FILE}"
        )

    hospitals = pd.read_csv(HOSPITALS_FILE)

    required_columns = {"hospital_name", "price_file_url"}
    missing_columns = required_columns - set(hospitals.columns)

    if missing_columns:
        raise ValueError(
            f"hospitals.csv is missing columns: {sorted(missing_columns)}"
        )

    print(f"Checking pricing sources from {HOSPITALS_FILE}\n")

    for _, hospital in hospitals.iterrows():
        check_url(
            hospital_name=hospital["hospital_name"],
            url=hospital["price_file_url"],
        )
        print()


if __name__ == "__main__":
    main()
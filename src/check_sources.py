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
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/149.0.0.0 Safari/537.36"
            ),
            "Accept": "text/csv,application/json,application/zip,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.northside.com/patients-visitors/billing-and-insurance/price-transparency",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Dest": "empty",
        }
        with requests.get(
            str(url).strip(),
            headers=headers,
            stream=True,
            timeout=30,
            allow_redirects=True,
        ) as response:

            if response.ok:
                print(f"SUCCESS: {hospital_name}")
            else:
                print(f"FAILED: {hospital_name}")

            print(f"  Status code: {response.status_code}")
            print(f"  Content type: {response.headers.get('Content-Type')}")
            print(f"  File size in bytes: {response.headers.get('Content-Length')}")
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
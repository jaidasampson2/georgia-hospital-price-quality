"""
Stream the large Northside MRF JSON and write a small, valid sample
containing the top-level metadata plus the first N charge records.
"""
from decimal import Decimal
import json
from pathlib import Path

import ijson

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "581954432-1457396079_northside-hospital-inc_standardcharges.json"
SAMPLE_FILE = PROJECT_ROOT / "data" / "sample" / "northside_sample.json"

N_RECORDS = 25


def build_sample() -> None:
    SAMPLE_FILE.parent.mkdir(parents=True, exist_ok=True)

    # First, grab the top-level metadata fields (everything except the
    # big standard_charge_information array) using a streaming parse.
    metadata = {}
    with open(RAW_FILE, "rb") as f:
        for prefix, event, value in ijson.parse(f):
            # Stop once we hit the start of the big array — we only
            # want the metadata fields that come before it.
            if prefix == "standard_charge_information" and event == "start_array":
                break
            if event in ("string", "number", "boolean", "null"):
                # Only capture top-level (non-nested) scalar fields.
                if "." not in prefix and prefix != "":
                    metadata[prefix] = value

    # Now stream just the first N items out of standard_charge_information.
    records = []
    with open(RAW_FILE, "rb") as f:
        items = ijson.items(f, "standard_charge_information.item")
        for i, item in enumerate(items):
            if i >= N_RECORDS:
                break
            records.append(item)

    sample = {**metadata, "standard_charge_information": records}

    def convert_decimals(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    with open(SAMPLE_FILE, "w") as f:
        json.dump(sample, f, indent=2, default=convert_decimals)

    print(f"Wrote {len(records)} records to {SAMPLE_FILE}")
    print(f"Sample file size: {SAMPLE_FILE.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    build_sample()
"""
Flatten the small Piedmont sample CSV into the same unified column schema
used for Northside, Emory, and Grady.

This script is adapted directly from flatten_emory_sample.py. Piedmont's
raw file uses the same flat, one-row-per-payer CMS layout Emory does
(unlike Grady's wide/pivoted structure), and the column names match
closely enough that no new extraction logic was needed -- just the
hospital name and file paths changed.

This script only reads the small sample file (data/sample/piedmont_sample.csv),
never the full ~75 MB ZIP file.
"""

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = PROJECT_ROOT / "data" / "sample" / "piedmont_sample.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "piedmont_sample_flat.csv"

HOSPITAL_NAME = "Piedmont Atlanta Hospital"

# Same column order as the other flatten_*.py scripts, so all hospitals'
# processed files can later be combined into one dataset.
OUTPUT_COLUMNS = [
    "hospital_name",
    "description",
    "ndc_code",
    "revenue_code",
    "cdm_code",
    "hcpcs_code",
    "cpt_code",
    "drg_code",
    "drug_unit",
    "drug_unit_type",
    "setting",
    "gross_charge",
    "discounted_cash",
    "minimum_charge",
    "maximum_charge",
    "payer_name",
    "plan_name",
    "negotiated_price",
    "methodology",
]

# Same code-type mapping used in flatten_emory_sample.py and
# flatten_grady_sample.py. Piedmont's sample also shows "LOCAL" as a code
# type (a hospital-internal code), which -- like APC -- doesn't map to
# one of our six standard columns, so it's intentionally dropped.
CODE_TYPE_TO_COLUMN = {
    "NDC": "ndc_code",
    "RC": "revenue_code",
    "CDM": "cdm_code",
    "HCPCS": "hcpcs_code",
    "CPT": "cpt_code",
    "DRG": "drg_code",
    "APC": None,
    "LOCAL": None,
}


def extract_codes(row: dict) -> dict:
    """Same logic as flatten_emory_sample.py / flatten_grady_sample.py."""
    codes = {column: "" for column in CODE_TYPE_TO_COLUMN.values() if column}

    for slot in range(1, 5):
        code_value = row.get(f"code|{slot}", "")
        code_type = row.get(f"code|{slot}|type", "")

        if not code_value or not code_type:
            continue

        column_name = CODE_TYPE_TO_COLUMN.get(code_type)
        if column_name:
            codes[column_name] = code_value
        # code_type values with no mapped column (APC, LOCAL) are
        # deliberately skipped rather than guessed into the wrong field.

    return codes


def flatten_row(row: dict) -> dict:
    """Map one row of Piedmont's raw CSV columns onto our unified schema."""
    codes = extract_codes(row)

    return {
        "hospital_name": HOSPITAL_NAME,
        "description": row.get("description", ""),
        **codes,
        "drug_unit": row.get("drug_unit_of_measurement", ""),
        "drug_unit_type": row.get("drug_type_of_measurement", ""),
        "setting": row.get("setting", ""),
        "gross_charge": row.get("standard_charge|gross", ""),
        "discounted_cash": row.get("standard_charge|discounted_cash", ""),
        "minimum_charge": row.get("standard_charge|min", ""),
        "maximum_charge": row.get("standard_charge|max", ""),
        "payer_name": row.get("payer_name", ""),
        "plan_name": row.get("plan_name", ""),
        # Unlike our Emory sample, Piedmont's sample has real numeric
        # values here for most rows -- so negotiated_price should NOT
        # come out mostly blank this time.
        "negotiated_price": row.get("standard_charge|negotiated_dollar", ""),
        "methodology": row.get("standard_charge|methodology", ""),
    }


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Could not find sample file at: {INPUT_FILE}")

    with open(INPUT_FILE, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = [flatten_row(row) for row in reader]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    blank_price_count = sum(1 for row in rows if not row["negotiated_price"])

    print(f"Read {len(rows)} rows from {INPUT_FILE.name}")
    print(f"Wrote {len(rows)} flat rows to {OUTPUT_FILE}")
    print(f"Rows with blank negotiated_price: {blank_price_count} of {len(rows)}")


if __name__ == "__main__":
    main()
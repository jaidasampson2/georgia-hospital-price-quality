"""
Flatten the small CHOA (Arthur M. Blank Hospital) sample CSV into the
unified column schema shared across all six hospitals in this project.

Two structural quirks specific to this file, different from the other
flat-CSV hospitals (Emory, Piedmont):

1. The min/max columns have SPACES around the pipe character:
   "standard_charge | min" and "standard_charge | max" -- not
   "standard_charge|min" like Emory/Piedmont/Wellstar. Column name
   lookups must match this exactly or they'll silently return blank.

2. This file uses "APR-DRG" as a code type (All Patient Refined DRG),
   not plain "DRG" like the other hospitals. Both are mapped to the same
   drg_code output column here.

This is the last of the six hospitals, and the only one negotiated_dollar
is populated on essentially every row -- CHOA is the most price-transparent
file in the dataset by a clear margin.
"""

import csv
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = PROJECT_ROOT / "data" / "sample" / "choa_sample.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "choa_sample_flat.csv"

HOSPITAL_NAME = "Arthur M. Blank Hospital"

# Same column order used across all six flatten_*.py scripts in this
# project, so every hospital's processed file can be combined into one
# dataset.
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
    "negotiated_percentage",
    "median_amount",
    "price_type",
    "resolved_price",
    "methodology",
]

# NOTE: "APR-DRG" added here, in addition to "DRG", both routing to the
# same drg_code column. Without this, every code in this file would be
# silently dropped, since it never uses plain "DRG" as a type.
CODE_TYPE_TO_COLUMN = {
    "NDC": "ndc_code",
    "RC": "revenue_code",
    "CDM": "cdm_code",
    "HCPCS": "hcpcs_code",
    "CPT": "cpt_code",
    "DRG": "drg_code",
    "APR-DRG": "drg_code",
    "APC": None,
    "LOCAL": None,
}


def extract_codes(row: dict) -> dict:
    codes = {column: "" for column in CODE_TYPE_TO_COLUMN.values() if column}
    for slot in range(1, 5):
        code_value = row.get(f"code|{slot}", "")
        code_type = row.get(f"code|{slot}|type", "")
        if not code_value or not code_type:
            continue
        column_name = CODE_TYPE_TO_COLUMN.get(code_type)
        if column_name:
            codes[column_name] = code_value
        # Unmapped types (APC, LOCAL) are deliberately dropped, same
        # convention as every other flatten_*.py script.
    return codes


def resolve_price(gross_charge: str, negotiated_dollar: str,
                   negotiated_percentage: str, median_amount: str) -> tuple:
    """Same priority logic used across all six hospitals: exact dollar >
    percentage-of-billed estimate > median estimate > unavailable."""
    if negotiated_dollar:
        return "negotiated_dollar", negotiated_dollar

    if negotiated_percentage and gross_charge:
        try:
            pct = float(negotiated_percentage)
            gross = float(gross_charge)
            estimated = round(gross * pct / 100, 2)
            return "percent_of_billed", str(estimated)
        except ValueError:
            pass

    if median_amount:
        return "median_estimate", median_amount

    return "unavailable", ""


def flatten_row(row: dict) -> dict:
    codes = extract_codes(row)

    gross_charge = row.get("standard_charge|gross", "")
    negotiated_dollar = row.get("standard_charge|negotiated_dollar", "")
    negotiated_percentage = row.get("standard_charge|negotiated_percentage", "")
    median_amount = row.get("median_amount", "")

    price_type, resolved_price = resolve_price(
        gross_charge, negotiated_dollar, negotiated_percentage, median_amount
    )

    return {
        "hospital_name": HOSPITAL_NAME,
        "description": row.get("description", ""),
        **codes,
        "drug_unit": row.get("drug_unit_of_measurement", ""),
        "drug_unit_type": row.get("drug_type_of_measurement", ""),
        "setting": row.get("setting", ""),
        "gross_charge": gross_charge,
        "discounted_cash": row.get("standard_charge|discounted_cash", ""),
        # NOTE the spaces around the pipe here -- matches this file's
        # actual header exactly ("standard_charge | min" / "... | max").
        "minimum_charge": row.get("standard_charge | min", ""),
        "maximum_charge": row.get("standard_charge | max", ""),
        "payer_name": row.get("payer_name", ""),
        "plan_name": row.get("plan_name", ""),
        "negotiated_price": negotiated_dollar,
        "negotiated_percentage": negotiated_percentage,
        "median_amount": median_amount,
        "price_type": price_type,
        "resolved_price": resolved_price,
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

    counts = Counter(row["price_type"] for row in rows)

    # Extra check specific to this hospital: how often gross_charge and
    # discounted_cash were identical, since that pattern showed up
    # repeatedly in the raw sample.
    identical_gross_and_cash = sum(
        1 for row in rows
        if row["gross_charge"] and row["gross_charge"] == row["discounted_cash"]
    )

    print(f"Read {len(rows)} rows from {INPUT_FILE.name}")
    print(f"Wrote {len(rows)} flat rows to {OUTPUT_FILE}")
    print(f"price_type breakdown: {dict(counts)}")
    print(f"Rows where gross_charge == discounted_cash: "
          f"{identical_gross_and_cash} of {len(rows)}")


if __name__ == "__main__":
    main()
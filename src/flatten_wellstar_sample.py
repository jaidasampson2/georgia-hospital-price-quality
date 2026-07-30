"""
Flatten the small Wellstar Kennestone sample CSV into the unified column
schema shared across all hospitals in this project.

UPDATE: same price resolution logic as flatten_emory_sample.py. This is
the hospital where the fallback logic matters most -- our second sample
showed heavy use of algorithm-based fee schedules, but with
median_amount / percentile fields populated even when negotiated_dollar
was blank. Expect a meaningful share of rows to resolve as
price_type = "median_estimate" here, in contrast to Piedmont's mostly
"negotiated_dollar" rows.
"""

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = PROJECT_ROOT / "data" / "sample" / "wellstar_sample.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "wellstar_sample_flat.csv"

HOSPITAL_NAME = "Wellstar Kennestone Hospital"

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
    codes = {column: "" for column in CODE_TYPE_TO_COLUMN.values() if column}
    for slot in range(1, 5):
        code_value = row.get(f"code|{slot}", "")
        code_type = row.get(f"code|{slot}|type", "")
        if not code_value or not code_type:
            continue
        column_name = CODE_TYPE_TO_COLUMN.get(code_type)
        if column_name:
            codes[column_name] = code_value
    return codes


def resolve_price(gross_charge: str, negotiated_dollar: str,
                   negotiated_percentage: str, median_amount: str) -> tuple:
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
        "minimum_charge": row.get("standard_charge|min", ""),
        "maximum_charge": row.get("standard_charge|max", ""),
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

    from collections import Counter
    counts = Counter(row["price_type"] for row in rows)

    print(f"Read {len(rows)} rows from {INPUT_FILE.name}")
    print(f"Wrote {len(rows)} flat rows to {OUTPUT_FILE}")
    print(f"price_type breakdown: {dict(counts)}")


if __name__ == "__main__":
    main()
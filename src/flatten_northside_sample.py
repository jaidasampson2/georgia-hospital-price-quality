"""
Flatten the small Northside sample JSON into the unified column schema
shared across all hospitals in this project.

UPDATE: same price resolution logic as the other flatten_*.py scripts.
Northside's JSON structure defines standard_charge_dollar directly on
each payer entry (and, per the CMS JSON schema, could alternatively use
standard_charge_percentage instead) -- but does not include a
median_amount equivalent the way the CSV-based hospitals do. So for
Northside specifically, expect price_type to only ever resolve as
"negotiated_dollar", "percent_of_billed", or "unavailable" -- never
"median_estimate". That's a real structural difference between the JSON
and CSV templates, worth noting in the audit.

BUGFIX: this script previously pulled hospital_name directly from the
JSON file's own "hospital_name" field, which is Northside's internal
corporate name ("Northside Hospital, Inc."), NOT the canonical name used
everywhere else in this project ("Northside Hospital Atlanta" --
matching config/hospitals.csv). That mismatch caused every Northside row
to silently fail to match any hospital in load_database.py. Now hardcoded
to the canonical name, same convention as every other flatten_*.py
script -- source files' self-reported names should never be trusted as
the join key.
"""

import json
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = PROJECT_ROOT / "data" / "sample" / "northside_sample.json"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "northside_sample_flat.csv"

# Canonical name, matching config/hospitals.csv -- NOT the same as the
# "hospital_name" field inside Northside's own JSON file, which is its
# internal corporate name ("Northside Hospital, Inc.") rather than the
# name used consistently across this project.
HOSPITAL_NAME = "Northside Hospital Atlanta"

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
}


def extract_codes(code_information: list) -> dict:
    codes = {column: "" for column in CODE_TYPE_TO_COLUMN.values()}
    for code_entry in code_information or []:
        code_type = code_entry.get("type")
        column_name = CODE_TYPE_TO_COLUMN.get(code_type)
        if column_name:
            codes[column_name] = code_entry.get("code", "")
    return codes


def resolve_price(gross_charge, negotiated_dollar,
                   negotiated_percentage, median_amount) -> tuple:
    if negotiated_dollar not in ("", None):
        return "negotiated_dollar", negotiated_dollar

    if negotiated_percentage not in ("", None) and gross_charge not in ("", None):
        try:
            pct = float(negotiated_percentage)
            gross = float(gross_charge)
            estimated = round(gross * pct / 100, 2)
            return "percent_of_billed", estimated
        except (ValueError, TypeError):
            pass

    if median_amount not in ("", None):
        return "median_estimate", median_amount

    return "unavailable", ""


def flatten_service(service: dict, hospital_name: str) -> list:
    rows = []

    description = service.get("description", "")
    codes = extract_codes(service.get("code_information"))

    drug_info = service.get("drug_information", {})
    drug_unit = drug_info.get("unit", "")
    drug_unit_type = drug_info.get("type", "")

    standard_charges = service.get("standard_charges", [])

    for charge in standard_charges:
        setting = charge.get("setting", "")
        gross_charge = charge.get("gross_charge", "")
        discounted_cash = charge.get("discounted_cash", "")
        minimum_charge = charge.get("minimum", "")
        maximum_charge = charge.get("maximum", "")

        payers = charge.get("payers_information", [])

        if not payers:
            rows.append({
                "hospital_name": hospital_name,
                "description": description,
                **codes,
                "drug_unit": drug_unit,
                "drug_unit_type": drug_unit_type,
                "setting": setting,
                "gross_charge": gross_charge,
                "discounted_cash": discounted_cash,
                "minimum_charge": minimum_charge,
                "maximum_charge": maximum_charge,
                "payer_name": "",
                "plan_name": "",
                "negotiated_price": "",
                "negotiated_percentage": "",
                "median_amount": "",
                "price_type": "unavailable",
                "resolved_price": "",
                "methodology": "",
            })
            continue

        for payer in payers:
            negotiated_dollar = payer.get("standard_charge_dollar", "")
            negotiated_percentage = payer.get("standard_charge_percentage", "")
            # Northside's JSON schema has no median_amount equivalent.
            median_amount = ""

            price_type, resolved_price = resolve_price(
                gross_charge, negotiated_dollar, negotiated_percentage, median_amount
            )

            rows.append({
                "hospital_name": hospital_name,
                "description": description,
                **codes,
                "drug_unit": drug_unit,
                "drug_unit_type": drug_unit_type,
                "setting": setting,
                "gross_charge": gross_charge,
                "discounted_cash": discounted_cash,
                "minimum_charge": minimum_charge,
                "maximum_charge": maximum_charge,
                "payer_name": payer.get("payer_name", ""),
                "plan_name": payer.get("plan_name", ""),
                "negotiated_price": negotiated_dollar,
                "negotiated_percentage": negotiated_percentage,
                "median_amount": median_amount,
                "price_type": price_type,
                "resolved_price": resolved_price,
                "methodology": payer.get("methodology", ""),
            })

    return rows


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Could not find sample file at: {INPUT_FILE}")

    with open(INPUT_FILE, "r") as f:
        data = json.load(f, parse_float=Decimal)

    # Use the canonical project-wide name, NOT data.get("hospital_name"),
    # which would pull Northside's own internal corporate name instead.
    hospital_name = HOSPITAL_NAME
    services = data.get("standard_charge_information", [])

    all_rows = []
    for service in services:
        all_rows.extend(flatten_service(service, hospital_name))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    import csv
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)

    from collections import Counter
    counts = Counter(row["price_type"] for row in all_rows)

    print(f"Read {len(services)} service records from {INPUT_FILE.name}")
    print(f"Wrote {len(all_rows)} flat rows to {OUTPUT_FILE}")
    print(f"price_type breakdown: {dict(counts)}")


if __name__ == "__main__":
    main()
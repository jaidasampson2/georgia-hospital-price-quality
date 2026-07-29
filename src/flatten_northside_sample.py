"""
Flatten the small Northside sample JSON file into a flat CSV.

Why this script exists:
The raw Northside file uses the CMS "tall" JSON format, which nests data
several levels deep: each service has a list of standard_charges (one per
care setting, e.g. inpatient/outpatient), and each of those has a list of
payers_information (one per payer+plan combination). SQL and Tableau both
want flat, row-per-record data, not nested JSON -- so this script "flattens"
the structure into one CSV row per (service, setting, payer) combination.

This script only reads the small sample file (data/sample/northside_sample.json),
never the full 906 MB raw file, so it's safe to run quickly and repeatedly
while developing the flattening logic.
"""

import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = PROJECT_ROOT / "data" / "sample" / "northside_sample.json"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "northside_sample_flat.csv"

# The column order for the output CSV. Defined once here so both the
# CSV header and every row we write stay in sync.
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

# Maps the "type" field found in each service's code_information list to
# the output column it should be written into. Not every service will have
# every code type -- most will only have 2-3 of these present.
CODE_TYPE_TO_COLUMN = {
    "NDC": "ndc_code",
    "RC": "revenue_code",
    "CDM": "cdm_code",
    "HCPCS": "hcpcs_code",
    "CPT": "cpt_code",
    "DRG": "drg_code",
}


def extract_codes(code_information: list) -> dict:
    """
    Given a service's code_information list (e.g.
    [{"code": "00338004303", "type": "NDC"}, {"code": "0250", "type": "RC"}]),
    return a dict with the six known code columns, filled in where present
    and left as an empty string where a given code type wasn't provided.
    """
    codes = {column: "" for column in CODE_TYPE_TO_COLUMN.values()}

    for code_entry in code_information or []:
        code_type = code_entry.get("type")
        column_name = CODE_TYPE_TO_COLUMN.get(code_type)
        if column_name:
            # If a service somehow lists the same code type twice, this
            # keeps the last one seen rather than crashing.
            codes[column_name] = code_entry.get("code", "")

    return codes


def flatten_service(service: dict, hospital_name: str) -> list:
    """
    Take one service record from standard_charge_information and expand it
    into a list of flat row dicts -- one row per (setting, payer) pair.

    A service with 2 settings (inpatient/outpatient) and 5 payers each
    would produce 10 rows here. A service with 1 setting and no payers
    listed produces exactly 1 row, with payer fields left blank.
    """
    rows = []

    description = service.get("description", "")
    codes = extract_codes(service.get("code_information"))

    # drug_information is only present for drug/medication line items,
    # not for procedures, supplies, etc. -- so we default to blank.
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
            # No payer-specific rates were listed for this setting at all
            # (this does happen in real hospital files). We still want a
            # row representing this charge -- just with payer fields blank
            # rather than silently dropping the record.
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
                "methodology": "",
            })
            continue

        # Normal case: one row per payer+plan negotiated rate.
        for payer in payers:
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
                "negotiated_price": payer.get("standard_charge_dollar", ""),
                "methodology": payer.get("methodology", ""),
            })

    return rows


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Could not find sample file at: {INPUT_FILE}")

    with open(INPUT_FILE, "r") as f:
        data = json.load(f)

    hospital_name = data.get("hospital_name", "")
    services = data.get("standard_charge_information", [])

    all_rows = []
    for service in services:
        all_rows.extend(flatten_service(service, hospital_name))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Read {len(services)} service records from {INPUT_FILE.name}")
    print(f"Wrote {len(all_rows)} flat rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
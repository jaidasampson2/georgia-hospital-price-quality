"""
Flatten the small Emory sample CSV into the same unified column schema
used for Northside (see flatten_northside_sample.py), so that data from
different hospitals -- even though their raw formats are completely
different -- can eventually be combined into one SQL table.

Why this is simpler than the Northside script:
Emory's CMS "wide" template is ALREADY flat -- one row per
(service, setting, payer, plan) combination, no nested JSON to unroll.
The real work here is just RENAMING and REMAPPING Emory's columns to
match the same output schema Northside uses, so both hospitals' data
lines up in the same shape afterward.

This script only reads the small sample file
(data/sample/emory_sample.csv), never the full ~54 MB raw file.
"""

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = PROJECT_ROOT / "data" / "sample" / "emory_sample.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "emory_sample_flat.csv"

# Emory's file itself doesn't repeat the hospital name on every row (it's
# only in the metadata rows we intentionally skipped when sampling), so
# we hardcode it here -- matching the value from config/hospitals.csv.
HOSPITAL_NAME = "Emory University Hospital"

# Must match the column order used in flatten_northside_sample.py exactly,
# so the two hospitals' processed files can later be concatenated into one
# combined dataset without any column mismatches.
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

# Emory's file uses 4 generic "code|N" / "code|N|type" column pairs,
# rather than Northside's single list of {code, type} objects. This maps
# each possible "type" value found in those columns to the output column
# it belongs in -- same idea as CODE_TYPE_TO_COLUMN in the Northside
# script, just applied to a differently-shaped input.
CODE_TYPE_TO_COLUMN = {
    "NDC": "ndc_code",
    "RC": "revenue_code",
    "CDM": "cdm_code",
    "HCPCS": "hcpcs_code",
    "CPT": "cpt_code",
    "DRG": "drg_code",
    "APC": None,  # APC codes don't have a matching column in our schema;
                  # intentionally dropped rather than guessed into one.
}


def extract_codes(row: dict) -> dict:
    """
    Emory's row has up to 4 code/type pairs: code|1 + code|1|type,
    code|2 + code|2|type, code|3 + code|3|type, code|4 + code|4|type.
    Walk through all 4 slots and route each present code to the correct
    output column based on its type.
    """
    codes = {column: "" for column in CODE_TYPE_TO_COLUMN.values() if column}

    for slot in range(1, 5):
        code_value = row.get(f"code|{slot}", "")
        code_type = row.get(f"code|{slot}|type", "")

        if not code_value or not code_type:
            continue

        column_name = CODE_TYPE_TO_COLUMN.get(code_type)
        if column_name:
            codes[column_name] = code_value
        # If column_name is None (e.g. "APC"), we deliberately skip it --
        # this row's code exists but doesn't map to one of our six
        # standard columns, so it's not silently invented into the
        # wrong field.

    return codes


def flatten_row(row: dict) -> dict:
    """
    Map one row of Emory's raw CSV columns onto our unified output schema.
    Because Emory's file is already one-row-per-payer, this is a direct
    field-by-field remap rather than an unrolling operation.
    """
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
        # NOTE: Emory often leaves standard_charge|negotiated_dollar blank
        # and instead stuffs the real rate into a free-text
        # standard_charge|negotiated_algorithm field (e.g. a fee schedule
        # written out in brackets). We only map the clean numeric dollar
        # field here -- rows with an algorithm-only rate will show up
        # with a blank negotiated_price, which is itself a real data
        # quality finding worth flagging in the audit, not a bug to hide.
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

    # Quick, visible data-quality signal while developing: how many rows
    # came through with no usable numeric negotiated price at all.
    blank_price_count = sum(1 for row in rows if not row["negotiated_price"])

    print(f"Read {len(rows)} rows from {INPUT_FILE.name}")
    print(f"Wrote {len(rows)} flat rows to {OUTPUT_FILE}")
    print(f"Rows with blank negotiated_price (likely algorithm/percentage-based): "
          f"{blank_price_count} of {len(rows)}")


if __name__ == "__main__":
    main()
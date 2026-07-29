"""
Flatten the small Grady sample CSV into the same unified column schema
used for Northside and Emory (see flatten_northside_sample.py and
flatten_emory_sample.py).

Why this script is different from the other two:
Northside needed UNROLLING nested JSON (one service -> many settings ->
many payers).
Emory needed simple REMAPPING (already one row per payer -- just rename
columns).
Grady needs UNPIVOTING (wide-to-long): each service is ONE row, but every
payer+plan combination is stored SIDEWAYS as its own group of 9 columns,
e.g.:
    standard_charge|Aetna|Commercial|negotiated_dollar
    standard_charge|Aetna|Commercial|negotiated_percentage
    standard_charge|Aetna|Commercial|negotiated_algorithm
    median_amount|Aetna|Commercial
    10th_percentile|Aetna|Commercial
    90th_percentile|Aetna|Commercial
    count|Aetna|Commercial
    standard_charge|Aetna|Commercial|methodology
    additional_payer_notes|Aetna|Commercial
...repeated for every payer+plan pair Grady contracts with (25+ of them
in this sample alone). Most of these 200+ columns are blank on any given
row, since a given service rarely has a rate from every possible payer.

This script scans the header to discover every payer+plan pair present,
then for each SERVICE ROW, walks through every payer+plan group and emits
one flat output row per (service, payer, plan) combination -- but only
when that payer+plan actually has SOME rate data, so we don't flood the
output with hundreds of entirely-blank rows per service.

This script only reads the small sample file (data/sample/grady_sample.csv),
never the full ~183 MB raw file.
"""

import csv
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = PROJECT_ROOT / "data" / "sample" / "grady_sample.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "grady_sample_flat.csv"

HOSPITAL_NAME = "Grady Memorial Hospital"

# Must match the column order used in the other two flatten_*.py scripts,
# so all three hospitals' processed files can later be combined into one
# dataset without column mismatches.
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

# Same code-type mapping used in flatten_emory_sample.py -- Grady's file
# uses the same code|1..4 / code|1|type..4|type pattern.
CODE_TYPE_TO_COLUMN = {
    "NDC": "ndc_code",
    "RC": "revenue_code",
    "CDM": "cdm_code",
    "HCPCS": "hcpcs_code",
    "CPT": "cpt_code",
    "DRG": "drg_code",
    "APC": None,
}

# Matches column names like "standard_charge|Aetna|Commercial|negotiated_dollar"
# and captures the payer name ("Aetna") and plan name ("Commercial").
# This is what lets us discover every payer+plan pair directly from the
# header, instead of hardcoding a list of Grady's specific payers.
PAYER_PLAN_PATTERN = re.compile(
    r"^standard_charge\|(?P<payer>[^|]+)\|(?P<plan>[^|]+)\|negotiated_dollar$"
)


def discover_payer_plan_pairs(fieldnames: list) -> list:
    """
    Scan the CSV header and return a list of (payer, plan) tuples, one
    for each payer+plan column group found. We anchor the search on the
    "negotiated_dollar" column specifically, since every payer+plan group
    has exactly one of those -- it's a reliable marker for "a new
    payer+plan group starts here."
    """
    pairs = []
    for name in fieldnames:
        match = PAYER_PLAN_PATTERN.match(name)
        if match:
            pairs.append((match.group("payer"), match.group("plan")))
    return pairs


def extract_codes(row: dict) -> dict:
    """Same logic as flatten_emory_sample.py -- Grady uses the same
    code|1..4 / code|1|type..4|type column pattern."""
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


def flatten_service_row(row: dict, payer_plan_pairs: list) -> list:
    """
    Take one row of Grady's raw CSV (one service) and unpivot it into a
    list of flat output rows -- one per payer+plan that actually has
    some rate data attached.
    """
    codes = extract_codes(row)

    shared_fields = {
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
    }

    output_rows = []

    for payer, plan in payer_plan_pairs:
        negotiated_dollar = row.get(
            f"standard_charge|{payer}|{plan}|negotiated_dollar", ""
        )
        negotiated_percentage = row.get(
            f"standard_charge|{payer}|{plan}|negotiated_percentage", ""
        )
        negotiated_algorithm = row.get(
            f"standard_charge|{payer}|{plan}|negotiated_algorithm", ""
        )
        methodology = row.get(
            f"standard_charge|{payer}|{plan}|methodology", ""
        )

        # If this payer+plan has no rate information at all for this
        # service, skip it entirely rather than emitting a mostly-blank
        # row. We check all three rate-representation fields, since
        # Grady (like Emory) sometimes only fills in a percentage or an
        # algorithm note rather than a clean dollar amount.
        if not negotiated_dollar and not negotiated_percentage and not negotiated_algorithm:
            continue

        output_rows.append({
            **shared_fields,
            "payer_name": payer,
            "plan_name": plan,
            # Only the clean numeric dollar amount is mapped to
            # negotiated_price, same convention as flatten_emory_sample.py.
            # Rows priced only by percentage or algorithm will have a
            # blank negotiated_price -- a real data quality signal, not
            # a bug, and worth surfacing in the audit rather than hiding.
            "negotiated_price": negotiated_dollar,
            "methodology": methodology,
        })

    return output_rows


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Could not find sample file at: {INPUT_FILE}")

    with open(INPUT_FILE, "r", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        payer_plan_pairs = discover_payer_plan_pairs(fieldnames)

        all_rows = []
        service_row_count = 0
        for row in reader:
            service_row_count += 1
            all_rows.extend(flatten_service_row(row, payer_plan_pairs))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)

    blank_price_count = sum(1 for row in all_rows if not row["negotiated_price"])

    print(f"Read {service_row_count} service rows from {INPUT_FILE.name}")
    print(f"Discovered {len(payer_plan_pairs)} payer+plan column groups in the header")
    print(f"Wrote {len(all_rows)} flat rows (payer+plan pairs with any rate data) "
          f"to {OUTPUT_FILE}")
    print(f"Rows with blank negotiated_price (percentage/algorithm-based instead): "
          f"{blank_price_count} of {len(all_rows)}")


if __name__ == "__main__":
    main()
"""
Flatten the small Grady sample CSV into the unified column schema shared
across all hospitals in this project.

UPDATE: added billing_class and modifiers. This is the exact discovery
that prompted this schema change project-wide: Grady's CPT 70450 data
showed multiple different prices for what looked like "the same"
service (same description, same CPT code) until billing_class and
modifiers were checked -- they revealed facility fee vs.
professional-interpretation-only (modifier 26) vs.
professional-technical-component-only (modifier TC) as genuinely
different billing entities. These are per-row fields (shared across all
of a row's payer+plan groups), same as gross_charge/setting.
"""

import csv
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = PROJECT_ROOT / "data" / "sample" / "grady_sample.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "grady_sample_flat.csv"

HOSPITAL_NAME = "Grady Memorial Hospital"

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
    "billing_class",
    "modifiers",
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
}

PAYER_PLAN_PATTERN = re.compile(
    r"^standard_charge\|(?P<payer>[^|]+)\|(?P<plan>[^|]+)\|negotiated_dollar$"
)


def discover_payer_plan_pairs(fieldnames: list) -> list:
    pairs = []
    for name in fieldnames:
        match = PAYER_PLAN_PATTERN.match(name)
        if match:
            pairs.append((match.group("payer"), match.group("plan")))
    return pairs


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


def flatten_service_row(row: dict, payer_plan_pairs: list) -> list:
    codes = extract_codes(row)

    gross_charge = row.get("standard_charge|gross", "")

    shared_fields = {
        "hospital_name": HOSPITAL_NAME,
        "description": row.get("description", ""),
        **codes,
        "drug_unit": row.get("drug_unit_of_measurement", ""),
        "drug_unit_type": row.get("drug_type_of_measurement", ""),
        "billing_class": row.get("billing_class", ""),
        "modifiers": row.get("modifiers", ""),
        "setting": row.get("setting", ""),
        "gross_charge": gross_charge,
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
        median_amount = row.get(f"median_amount|{payer}|{plan}", "")
        methodology = row.get(f"standard_charge|{payer}|{plan}|methodology", "")

        if not (negotiated_dollar or negotiated_percentage
                or negotiated_algorithm or median_amount):
            continue

        price_type, resolved_price = resolve_price(
            gross_charge, negotiated_dollar, negotiated_percentage, median_amount
        )

        output_rows.append({
            **shared_fields,
            "payer_name": payer,
            "plan_name": plan,
            "negotiated_price": negotiated_dollar,
            "negotiated_percentage": negotiated_percentage,
            "median_amount": median_amount,
            "price_type": price_type,
            "resolved_price": resolved_price,
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

    from collections import Counter
    counts = Counter(row["price_type"] for row in all_rows)

    print(f"Read {service_row_count} service rows from {INPUT_FILE.name}")
    print(f"Discovered {len(payer_plan_pairs)} payer+plan column groups in the header")
    print(f"Wrote {len(all_rows)} flat rows to {OUTPUT_FILE}")
    print(f"price_type breakdown: {dict(counts)}")


if __name__ == "__main__":
    main()
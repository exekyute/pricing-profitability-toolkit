"""Command-line wrapper for the tiered pricing engine.

Reads a product cost master CSV, validates it, builds the tiered wholesale
pricing schedule, prints a readable table, and writes the schedule to CSV.

Run from inside this folder:

    python cli.py
    python cli.py --input data/sample_products.csv --output out/pricing_schedule.csv
    python cli.py --input data/invalid_products.csv

The logic lives in pricing_engine_logic.py. This file only handles input,
output, and formatting.
"""

import argparse
import csv
import os
import sys

from pricing_engine_logic import (
    ValidationError,
    load_products,
    build_schedule,
)

DEFAULT_INPUT = os.path.join("data", "sample_products.csv")
DEFAULT_OUTPUT = os.path.join("out", "pricing_schedule.csv")

SCHEDULE_COLUMNS = [
    "sku",
    "product_name",
    "unit_cost",
    "tier_label",
    "min_quantity",
    "target_margin",
    "wholesale_price",
    "achieved_margin",
]


def read_csv(path):
    """Read a CSV into (rows, fieldnames). Raises ValidationError if missing."""
    if not os.path.isfile(path):
        raise ValidationError(["input file not found: {0}".format(path)])
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return rows, reader.fieldnames


def write_schedule(path, schedule):
    """Write schedule rows to CSV with fixed-point Decimal text."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SCHEDULE_COLUMNS)
        writer.writeheader()
        for row in schedule:
            writer.writerow(
                {
                    "sku": row["sku"],
                    "product_name": row["product_name"],
                    "unit_cost": "{0:.2f}".format(row["unit_cost"]),
                    "tier_label": row["tier_label"],
                    "min_quantity": row["min_quantity"],
                    "target_margin": "{0:.4f}".format(row["target_margin"]),
                    "wholesale_price": "{0:.2f}".format(row["wholesale_price"]),
                    "achieved_margin": "{0:.4f}".format(row["achieved_margin"]),
                }
            )


def percent(margin_fraction):
    """Format a Decimal fraction (0.4000) as a fixed-point percent (40.00%)."""
    return "{0:.2f}%".format(margin_fraction * 100)


def print_table(schedule):
    """Print the schedule as an aligned console table."""
    header = [
        "SKU",
        "PRODUCT",
        "COST",
        "TIER",
        "MIN QTY",
        "TARGET",
        "PRICE",
        "ACHIEVED",
    ]
    rows = [header]
    for row in schedule:
        rows.append(
            [
                row["sku"],
                row["product_name"],
                "{0:.2f}".format(row["unit_cost"]),
                row["tier_label"],
                str(row["min_quantity"]),
                percent(row["target_margin"]),
                "{0:.2f}".format(row["wholesale_price"]),
                percent(row["achieved_margin"]),
            ]
        )

    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    for line_index, row in enumerate(rows):
        cells = [row[i].ljust(widths[i]) for i in range(len(row))]
        print("  ".join(cells))
        if line_index == 0:
            print("  ".join("-" * widths[i] for i in range(len(header))))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build a tiered wholesale pricing schedule from a product cost master."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT, help="product master CSV")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="schedule output CSV")
    args = parser.parse_args(argv)

    try:
        rows, fieldnames = read_csv(args.input)
        products = load_products(rows, fieldnames)
    except ValidationError as error:
        print("Input rejected. Fix these problems and run again:", file=sys.stderr)
        for problem in error.problems:
            print("  - {0}".format(problem), file=sys.stderr)
        return 1

    schedule = build_schedule(products)
    print_table(schedule)
    write_schedule(args.output, schedule)
    print("")
    print(
        "Built {0} products x 3 tiers = {1} schedule rows.".format(
            len(products), len(schedule)
        )
    )
    print("Schedule written to {0}".format(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())

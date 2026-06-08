"""Command-line wrapper for the product cost sensitivity simulator.

Reads the approved pricing schedule (tool 1 output), applies a raw material cost
increase, and reports the impact on each product's gross margin while holding
the wholesale price constant.

Run from inside this folder:

    python cli.py --increase 8
    python cli.py --increase 8 --threshold 0.30
    python cli.py --increase 0
    python cli.py --increase abc

The logic lives in sensitivity_logic.py. This file only handles input, output,
and formatting.
"""

import argparse
import csv
import os
import sys
from decimal import Decimal, InvalidOperation

from sensitivity_logic import (
    ValidationError,
    load_schedule,
    simulate,
    summarize,
    DEFAULT_THRESHOLD,
    STATUS_OK,
    STATUS_BELOW_THRESHOLD,
    STATUS_ALREADY_BELOW,
)

DEFAULT_SCHEDULE = os.path.join("data", "approved_pricing_schedule.csv")
DEFAULT_OUTPUT = os.path.join("out", "sensitivity_report.csv")

REPORT_COLUMNS = [
    "sku",
    "product_name",
    "tier_label",
    "old_cost",
    "new_cost",
    "wholesale_price",
    "old_margin",
    "new_margin",
    "margin_delta",
    "status",
]


def read_csv(path, label):
    if not os.path.isfile(path):
        raise ValidationError(["{0} file not found: {1}".format(label, path)])
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader), reader.fieldnames


def money(value):
    return "{0:.2f}".format(value)


def percent(value):
    return "{0:.2f}%".format(value * 100)


def signed_percent(value):
    return "{0:+.2f}%".format(value * 100)


def fraction(value):
    return "{0:.4f}".format(value)


def write_report(path, results):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        for row in results:
            writer.writerow(
                {
                    "sku": row["sku"],
                    "product_name": row["product_name"],
                    "tier_label": row["tier_label"],
                    "old_cost": money(row["old_cost"]),
                    "new_cost": money(row["new_cost"]),
                    "wholesale_price": money(row["wholesale_price"]),
                    "old_margin": fraction(row["old_margin"]),
                    "new_margin": fraction(row["new_margin"]),
                    "margin_delta": fraction(row["margin_delta"]),
                    "status": row["status"],
                }
            )


def print_table(results):
    header = ["SKU", "PRODUCT", "TIER", "OLD COST", "NEW COST", "OLD MARGIN", "NEW MARGIN", "DELTA", "STATUS"]
    rows = [header]
    for row in results:
        rows.append(
            [
                row["sku"],
                row["product_name"],
                row["tier_label"],
                money(row["old_cost"]),
                money(row["new_cost"]),
                percent(row["old_margin"]),
                percent(row["new_margin"]),
                signed_percent(row["margin_delta"]),
                row["status"],
            ]
        )
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    for line_index, row in enumerate(rows):
        print("  ".join(row[i].ljust(widths[i]) for i in range(len(row))))
        if line_index == 0:
            print("  ".join("-" * widths[i] for i in range(len(header))))


def print_summary(summary, increase_pct, threshold):
    print("")
    print("Applied a {0:+.2f}% raw material cost increase, holding wholesale prices constant.".format(increase_pct))
    print("Company gross margin floor: {0:.2f}%".format(threshold * 100))
    print("Of {0} product tiers:".format(summary["total"]))
    print("  Still above the floor:        {0}".format(summary[STATUS_OK]))
    print("  Newly below after increase:   {0}".format(summary[STATUS_BELOW_THRESHOLD]))
    print("  Already below before increase: {0}".format(summary[STATUS_ALREADY_BELOW]))


def parse_decimal_arg(raw, name):
    try:
        return Decimal(raw)
    except InvalidOperation:
        raise ValidationError(["{0} '{1}' is not a number".format(name, raw)])


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Show the gross margin impact of a raw material cost increase on the approved schedule."
    )
    parser.add_argument("--increase", default="0", help="raw material cost increase percent, e.g. 8 or 8.5 (negatives allowed)")
    parser.add_argument("--schedule", default=DEFAULT_SCHEDULE, help="approved pricing schedule CSV")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="sensitivity report output CSV")
    parser.add_argument("--threshold", default=None, help="company gross margin floor (0 to 1), default 0.33")
    args = parser.parse_args(argv)

    try:
        increase_pct = parse_decimal_arg(args.increase, "--increase")
        threshold = DEFAULT_THRESHOLD if args.threshold is None else parse_decimal_arg(args.threshold, "--threshold")
        schedule_rows, schedule_fields = read_csv(args.schedule, "pricing schedule")
        products = load_schedule(schedule_rows, schedule_fields)
        results = simulate(products, increase_pct, threshold)
    except ValidationError as error:
        print("Simulation could not run. Fix these problems:", file=sys.stderr)
        for problem in error.problems:
            print("  - {0}".format(problem), file=sys.stderr)
        return 1

    print_table(results)
    summary = summarize(results)
    print_summary(summary, increase_pct, threshold)
    write_report(args.output, results)
    print("Report written to {0}".format(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())

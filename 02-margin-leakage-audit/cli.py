"""Command-line wrapper for the margin leakage audit.

Reads a transaction ledger and the approved pricing schedule (tool 1 output),
audits every sale, prints a per-transaction report, and writes it to CSV.

Run from inside this folder:

    python cli.py
    python cli.py --ledger data/transactions_ledger.csv --schedule data/approved_pricing_schedule.csv
    python cli.py --threshold 0.35
    python cli.py --ledger data/broken_ledger.csv

The logic lives in audit_logic.py. This file only handles input, output, and
formatting.
"""

import argparse
import csv
import os
import sys
from decimal import Decimal, InvalidOperation

from audit_logic import (
    ValidationError,
    load_schedule,
    audit_ledger,
    summarize,
    STATUS_OK,
    STATUS_FLAGGED,
    STATUS_UNKNOWN_SKU,
    STATUS_DUPLICATE,
    STATUS_ERROR,
)

DEFAULT_LEDGER = os.path.join("data", "transactions_ledger.csv")
DEFAULT_SCHEDULE = os.path.join("data", "approved_pricing_schedule.csv")
DEFAULT_OUTPUT = os.path.join("out", "audit_report.csv")

REPORT_COLUMNS = [
    "txn_id",
    "sku",
    "order_quantity",
    "unit_sale_price",
    "unit_cost",
    "tier_label",
    "target_margin",
    "actual_margin",
    "status",
    "leakage",
    "note",
]


def read_csv(path, label):
    if not os.path.isfile(path):
        raise ValidationError(["{0} file not found: {1}".format(label, path)])
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader), reader.fieldnames


def money(value):
    return "" if value is None else "{0:.2f}".format(value)


def percent(value):
    return "" if value is None else "{0:.2f}%".format(value * 100)


def fraction(value):
    return "" if value is None else "{0:.4f}".format(value)


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
                    "txn_id": row["txn_id"],
                    "sku": row["sku"],
                    "order_quantity": "" if row["order_quantity"] is None else row["order_quantity"],
                    "unit_sale_price": money(row["unit_sale_price"]),
                    "unit_cost": money(row["unit_cost"]),
                    "tier_label": row["tier_label"],
                    "target_margin": fraction(row["target_margin"]),
                    "actual_margin": fraction(row["actual_margin"]),
                    "status": row["status"],
                    "leakage": money(row["leakage"]),
                    "note": row["note"],
                }
            )


def print_report(results):
    header = ["TXN", "SKU", "QTY", "SALE", "COST", "TIER", "TARGET", "ACTUAL", "STATUS", "LEAKAGE"]
    rows = [header]
    for row in results:
        rows.append(
            [
                row["txn_id"],
                row["sku"],
                "" if row["order_quantity"] is None else str(row["order_quantity"]),
                money(row["unit_sale_price"]),
                money(row["unit_cost"]),
                row["tier_label"],
                percent(row["target_margin"]),
                percent(row["actual_margin"]),
                row["status"],
                money(row["leakage"]),
            ]
        )
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    for line_index, row in enumerate(rows):
        print("  ".join(row[i].ljust(widths[i]) for i in range(len(row))))
        if line_index == 0:
            print("  ".join("-" * widths[i] for i in range(len(header))))

    # Notes are printed under the table so flagged and error rows explain themselves.
    notes = [(r["txn_id"] or "(no id)", r["note"]) for r in results if r["note"]]
    if notes:
        print("")
        print("Notes:")
        for txn_id, note in notes:
            print("  {0}: {1}".format(txn_id, note))


def print_summary(summary):
    print("")
    print("Audited {0} transactions:".format(summary["total"]))
    print("  OK:          {0}".format(summary[STATUS_OK]))
    print("  Flagged:     {0}".format(summary[STATUS_FLAGGED]))
    print("  Unknown sku: {0}".format(summary[STATUS_UNKNOWN_SKU]))
    print("  Duplicate:   {0}".format(summary[STATUS_DUPLICATE]))
    print("  Error:       {0}".format(summary[STATUS_ERROR]))
    print("Total margin leakage: ${0:.2f}".format(summary["total_leakage"]))


def parse_threshold(raw):
    if raw is None:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise ValidationError(["--threshold '{0}' is not a number".format(raw)])
    if not (Decimal("0") <= value < Decimal("1")):
        raise ValidationError(["--threshold must be between 0 and 1 (got {0})".format(value)])
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit a transaction ledger for sales that fell below the approved gross margin."
    )
    parser.add_argument("--ledger", default=DEFAULT_LEDGER, help="transaction ledger CSV")
    parser.add_argument("--schedule", default=DEFAULT_SCHEDULE, help="approved pricing schedule CSV")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="audit report output CSV")
    parser.add_argument(
        "--threshold",
        default=None,
        help="optional global margin threshold (0 to 1) overriding each tier's target",
    )
    args = parser.parse_args(argv)

    try:
        threshold = parse_threshold(args.threshold)
        schedule_rows, schedule_fields = read_csv(args.schedule, "pricing schedule")
        schedule_index = load_schedule(schedule_rows, schedule_fields)
        ledger_rows, ledger_fields = read_csv(args.ledger, "ledger")
        results = audit_ledger(ledger_rows, ledger_fields, schedule_index, threshold)
    except ValidationError as error:
        print("Audit could not run. Fix these problems:", file=sys.stderr)
        for problem in error.problems:
            print("  - {0}".format(problem), file=sys.stderr)
        return 1

    print_report(results)
    summary = summarize(results)
    print_summary(summary)
    write_report(args.output, results)
    print("Report written to {0}".format(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())

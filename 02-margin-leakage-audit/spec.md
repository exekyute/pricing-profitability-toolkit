# Spec: Margin Leakage Audit

## Purpose

Audit a transaction ledger against the approved pricing schedule and flag any
sale whose actual gross margin fell below the approved target for that product
and volume tier. The flagged rows are where margin leaked out of the business.

## Inputs

- A transaction ledger CSV with columns `txn_id`, `sku`, `order_quantity`,
  `unit_sale_price`, `unit_cost`. Default: `data/transactions_ledger.csv`.
- The approved pricing schedule CSV produced by tool 1, with columns `sku`,
  `tier_label`, `min_quantity`, `target_margin`, `wholesale_price` (others are
  ignored). Default: `data/approved_pricing_schedule.csv`, a committed copy of
  tool 1's output so this tool runs on its own.
- Command-line options: `--ledger`, `--schedule`, `--output`, and an optional
  `--threshold` (a margin between 0 and 1) that overrides every tier's target
  with one company-wide bar.

## Validation rules

Two layers, on purpose:

- **File level (stops the run).** Each file must exist. The ledger must contain
  every required column and the schedule must contain its required columns. A
  bad `--threshold` value is also rejected here.
- **Row level (does not stop the run).** A single transaction with a missing or
  non-numeric `order_quantity`, `unit_sale_price`, or `unit_cost`, or a missing
  `txn_id`, is marked `ERROR` and the audit continues. One bad record should not
  hide the rest of the ledger.

## Logic

All money and margin math uses `decimal.Decimal` with `ROUND_HALF_UP`.

For each transaction:

1. If the `txn_id` was already seen, mark it `DUPLICATE` and stop there.
2. Parse the numeric fields. On failure, mark `ERROR`.
3. Look up the `sku` in the schedule. If absent, mark `UNKNOWN_SKU`.
4. Pick the volume tier: the highest tier whose `min_quantity` the order meets.
5. Compute `actual_margin = (unit_sale_price - unit_cost) / unit_sale_price`.
6. Compare against the target (the tier's `target_margin`, or `--threshold` if
   given). If `actual_margin` is below the target, mark `FLAGGED`; equal or above
   is `OK`.
7. For flagged rows, `leakage = (wholesale_price - unit_sale_price) *
   order_quantity`, floored at 0.

## Outputs

- A console report, one line per transaction: txn, sku, quantity, sale price,
  cost, tier, target margin, actual margin, status, leakage. Below it, a notes
  list explaining every flagged, unknown, duplicate, and error row.
- A summary: counts by status and total margin leakage in dollars.
- An audit report CSV (default `out/audit_report.csv`) with the same columns
  plus the note text.

Money prints to the cent and margins as fixed-point percent. No scientific
notation.

## Edge cases

The sample ledger is built so a single run exercises every status:

- **Boundary, not flagged (cross-tool agreement).** `T-001` sells `SKU-1001` at
  `20.00`. The margin is `(20.00 - 12.00) / 20.00 = 0.4000 = 40.00%`, exactly the
  Tier 1 target tool 1 set. Equal to target is not leakage, so it stays `OK`.
  This is the hand-checked value proving tool 1 and tool 2 agree: tool 1 prices
  `SKU-1001` Tier 1 at `20.00`, and tool 2 reads that same sale back as `40.00%`.
- **Flagged with leakage.** `T-002` sells the same product at `19.00`, a
  `36.84%` margin, below target. Leakage is `(20.00 - 19.00) * 50 = 50.00`.
- **Clean, comfortably above target.** `T-003` earns `42.69%` against a `35.00%`
  Tier 2 target.
- **Unknown sku.** `T-005` references `SKU-9999`, which is not in the schedule.
- **Duplicate.** The second `T-001` repeats an id already seen.
- **Row error.** `T-006` has a sale price of `0.00`, which cannot yield a margin,
  so the row is marked `ERROR` and the run continues.
- **Broken file.** `data/broken_ledger.csv` omits the `unit_cost` column, so the
  whole run is rejected before any row is audited.

Total margin leakage across the sample run is `$63.35` (`50.00` plus `13.35`).

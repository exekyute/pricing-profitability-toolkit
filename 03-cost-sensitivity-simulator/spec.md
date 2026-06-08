# Spec: Product Cost Sensitivity Simulator

## Purpose

Show how a raw material cost increase compresses gross margins. The user enters a
percentage increase, and the tool applies it to every product in the approved
pricing schedule, holds each wholesale price constant, and reports the resulting
margin alongside the original. Products that fall under the company margin floor
are called out.

## Inputs

- The approved pricing schedule CSV produced by tool 1, with columns `sku`,
  `tier_label`, `unit_cost`, `wholesale_price` (others are ignored, but
  `product_name` is used for display). Default:
  `data/approved_pricing_schedule.csv`, a committed copy of tool 1's output so
  this tool runs on its own.
- Command-line options:
  - `--increase`: the raw material cost change in percent, for example `8` or
    `8.5`. Negative values are allowed and model a cost decrease. Default `0`.
  - `--threshold`: the company gross margin floor between 0 and 1. Default `0.33`.
  - `--schedule`, `--output`.

## Validation rules

The run aborts with a clear message if any of these fail:

- The schedule file exists and contains the required columns.
- `--increase` parses as a number and is greater than -100 percent. A drop of
  100 percent or more would push cost to zero or below.
- `--threshold` parses as a number between 0 and 1.

## Logic

All money and margin math uses `decimal.Decimal` with `ROUND_HALF_UP`.

For each schedule row:

- `old_margin = (wholesale_price - unit_cost) / wholesale_price`.
- `new_cost = unit_cost * (1 + increase / 100)`, rounded to the cent.
- `new_margin = (wholesale_price - new_cost) / wholesale_price`.
- `margin_delta = new_margin - old_margin`.
- Status:
  - `ALREADY_BELOW` if the product was under the floor before the increase.
  - `BELOW_THRESHOLD` if the increase pushed it under the floor.
  - `OK` if it stays at or above the floor.

The wholesale price is deliberately held constant. The point is to see how much
margin a fixed price book gives up when input costs move, which is the question
behind any supply-chain cost negotiation.

## Outputs

- A console table, one line per product and tier: sku, product, tier, old cost,
  new cost, old margin, new margin, signed margin change, status.
- A summary: the increase applied, the floor in use, and counts of rows still
  above the floor, newly below, and already below.
- A report CSV (default `out/sensitivity_report.csv`) with the same columns.

Money prints to the cent and margins as fixed-point percent. No scientific
notation.

## Edge cases

- **Zero increase (sanity check and cross-tool agreement).** With `--increase 0`,
  the new cost equals the old cost and the new margin equals the original. For
  `SKU-1001` Tier 1 this reads `40.00%`, the exact margin tool 1 set when it
  priced that product to `20.00`. Running tool 3 at zero increase reproduces tool
  1's achieved margins, which is the documented agreement between the two tools.
- **Clean three-way split at +8%.** With the default `0.33` floor and an `8`
  percent increase, every Tier 1 row stays `OK`, every Tier 2 row crosses to
  `BELOW_THRESHOLD`, and every Tier 3 row is `ALREADY_BELOW` because the 30
  percent tier was under the company floor to begin with. One run shows all three
  outcomes.
- **Cost decrease.** A negative increase, for example `--increase -10`, lowers
  cost and lifts margin, with positive deltas.
- **Bad input.** `--increase abc` is rejected as not a number, and
  `--increase -150` is rejected because cost cannot fall by more than 100 percent.

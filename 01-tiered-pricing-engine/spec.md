# Spec: Tiered Pricing Engine

## Purpose

Turn a product cost master into a tiered wholesale pricing schedule. For each
product the tool sets a price at every volume tier so the sale earns the target
gross margin for that tier. Higher volume tiers carry a thinner target margin,
the usual wholesale trade-off.

## Inputs

- A product master CSV with columns `sku`, `product_name`, `unit_cost`.
  Default file: `data/sample_products.csv`.
- Volume tiers, defined in code (no input needed to run):

  | Tier   | Minimum order quantity | Target gross margin |
  |--------|------------------------|---------------------|
  | Tier 1 | 1                      | 40%                 |
  | Tier 2 | 100                    | 35%                 |
  | Tier 3 | 500                    | 30%                 |

- Command-line options: `--input` (master CSV), `--output` (schedule CSV,
  default `out/pricing_schedule.csv`).

## Validation rules

The run aborts and lists every problem at once if any of these fail:

- The input file exists and is readable.
- The header contains all required columns: `sku`, `product_name`, `unit_cost`.
- `sku` is present on every row and unique across the file.
- `unit_cost` parses as a number and is greater than 0.
- The file contains at least one data row.

Each problem is reported with the line number it came from.

## Logic

All money and margin math uses `decimal.Decimal` with `ROUND_HALF_UP`.

For each product, for each tier:

- `wholesale_price = unit_cost / (1 - target_margin)`, rounded to 2 places.
- `achieved_margin = (wholesale_price - unit_cost) / wholesale_price`, kept to
  4 places.

The achieved margin is reported alongside the target because rounding the price
to whole cents shifts the real margin by a fraction of a percent. Showing both
proves the schedule is internally consistent rather than hiding the rounding.

## Outputs

- A console table: SKU, product, cost, tier, minimum quantity, target margin,
  price, achieved margin. Margins print as fixed-point percent (for example
  `40.00%`); money prints to the cent (for example `20.00`). No scientific
  notation.
- A schedule CSV with columns `sku`, `product_name`, `unit_cost`, `tier_label`,
  `min_quantity`, `target_margin`, `wholesale_price`, `achieved_margin`. Margins
  are stored as 4-place fractions (for example `0.4000`) so downstream tools can
  read them directly.
- A summary line: products x 3 tiers = total rows.

A curated copy of one clean run is committed at `data/pricing_schedule.csv`. The
margin leakage audit (tool 2) and the cost sensitivity simulator (tool 3) read
that file as their approved pricing reference.

## Edge cases

- **Clean exact price.** `SKU-1001` costs `12.00`. At Tier 1 the price is
  `12.00 / (1 - 0.40) = 20.00` exactly, and the achieved margin is `40.00%`.
  This is the hand-checked value the margin leakage audit agrees with: a ledger
  sale of `SKU-1001` at `20.00` reads back `40.00%` and is not flagged.
- **Rounding deviation.** `SKU-1002` costs `10.00`. At Tier 1 the price rounds
  from `16.6667` to `16.67`, so the achieved margin is `40.01%`, slightly above
  target. The tool reports the real figure rather than the rounded-away `40.00%`.
- **Small cost.** `SKU-1005` costs `0.85`, where rounding to the cent moves the
  margin the most (Tier 1 achieves `40.14%`). This shows the limit of cent
  pricing on low-cost items.
- **Bad data.** `data/invalid_products.csv` holds a zero cost, a negative cost,
  a non-numeric cost, a duplicate sku, a missing sku, and a missing cost. A run
  against it is rejected with one message per problem.

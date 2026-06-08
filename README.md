# Pricing and Profitability Toolkit

A personal project, one of several I build to model real world job descriptions
and turn them into functional business utilities. The goal is to practice applied
problem solving on the kind of work a pricing and profitability analyst does,
while strengthening my foundational software development skills.

The repository holds three small command-line tools written in plain Python.
Each one is self contained, rule based, and built around clean business logic,
careful input validation, and exact money math. There is no AI, no machine
learning, and no outside libraries. Every cost, price, and margin figure is
computed with `decimal.Decimal` and printed in fixed-point form.

## The three tools

They are numbered because they build on each other. Start with tool 1, since
tools 2 and 3 read the pricing schedule it produces.

1. **[Tiered Pricing Engine](01-tiered-pricing-engine/)** turns a product cost
   master into a tiered wholesale pricing schedule, setting a price per volume
   tier to hit each tier's target gross margin and reporting the margin actually
   achieved after rounding.
2. **[Margin Leakage Audit](02-margin-leakage-audit/)** reads a transaction
   ledger and flags any sale whose gross margin fell below the approved target
   for its volume tier, then totals the leakage.
3. **[Cost Sensitivity Simulator](03-cost-sensitivity-simulator/)** applies a raw
   material cost increase to the schedule, holds wholesale prices constant, and
   shows how far each product moves toward or below the company margin floor.

## How they connect

Tool 1 produces an approved pricing schedule. Tools 2 and 3 each read a copy of
that schedule, so the three tools tell one continuous story: set prices, check
whether real sales held the line, then test what a supply cost change would do to
those same products.

The tools agree on a hand-checked number. Tool 1 prices `SKU-1001` at Tier 1 to
`20.00`, targeting a 40 percent margin. Tool 2 audits a real sale of `SKU-1001`
at `20.00` and reads it back as exactly `40.00%`, so it is not flagged. Tool 3,
run with a zero percent increase, reproduces that same `40.00%` from the
schedule. The figure is documented in each tool's `spec.md`.

## Running any tool

Each tool needs only Python 3 and the standard library. From inside a tool's
folder:

```
python -m unittest -v        run the tests
python cli.py --help         see the options
```

Each tool folder has its own README with worked examples and screenshots, a
`spec.md` describing inputs, validation, logic, outputs, and edge cases, sample
data, and a unit test suite.

## Repository layout

```
pricing-profitability-toolkit/
  LICENSE
  README.md
  01-tiered-pricing-engine/
  02-margin-leakage-audit/
  03-cost-sensitivity-simulator/
```

## License

Released under the MIT License. See [LICENSE](LICENSE).
Copyright (c) 2026 Kevin Yu (https://github.com/exekyute).

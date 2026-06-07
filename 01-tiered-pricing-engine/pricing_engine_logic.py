"""Pure business logic for the tiered pricing engine.

This module holds the calculation and validation rules only. It does not read
files, print, or touch the command line. That keeps the rules easy to test with
fixed numbers and easy to reuse from the thin CLI wrapper in cli.py.

All money and margin math uses decimal.Decimal with ROUND_HALF_UP so results are
exact to the cent and never appear in scientific notation.
"""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

# Quantizers. Prices land on cents (2 places); margins keep 4 places so a small
# rounding deviation between target and achieved margin stays visible.
MONEY = Decimal("0.01")
MARGIN = Decimal("0.0001")

# Columns every product master file must provide.
REQUIRED_COLUMNS = ["sku", "product_name", "unit_cost"]

# Default volume tiers: (label, minimum order quantity, target gross margin).
# Higher volume earns a thinner margin, the usual wholesale trade-off.
DEFAULT_TIERS = [
    ("Tier 1", 1, Decimal("0.40")),
    ("Tier 2", 100, Decimal("0.35")),
    ("Tier 3", 500, Decimal("0.30")),
]


class ValidationError(Exception):
    """Raised when the input data breaks a rule. Carries a list of messages so
    the CLI can show every problem at once instead of one at a time."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def quantize_money(value):
    """Round a Decimal to cents, half up."""
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def quantize_margin(value):
    """Round a Decimal margin fraction to 4 places, half up."""
    return value.quantize(MARGIN, rounding=ROUND_HALF_UP)


def compute_wholesale_price(unit_cost, target_margin):
    """Price that yields the target gross margin, rounded to cents.

    price = cost / (1 - target_margin)
    """
    if target_margin >= Decimal("1"):
        raise ValidationError(["target margin must be below 1 (100%)"])
    price = unit_cost / (Decimal("1") - target_margin)
    return quantize_money(price)


def compute_achieved_margin(wholesale_price, unit_cost):
    """Actual gross margin earned at the rounded price.

    achieved = (price - cost) / price

    This can differ slightly from the target because the price was rounded to
    cents. Reporting it proves the schedule is internally consistent.
    """
    if wholesale_price <= Decimal("0"):
        raise ValidationError(["wholesale price must be positive"])
    achieved = (wholesale_price - unit_cost) / wholesale_price
    return quantize_margin(achieved)


def _parse_positive_decimal(raw, field_name, line_number):
    """Parse a cell into a positive Decimal or return an error message."""
    text = (raw or "").strip()
    if text == "":
        return None, "line {0}: {1} is missing".format(line_number, field_name)
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None, "line {0}: {1} '{2}' is not a number".format(
            line_number, field_name, text
        )
    if value <= Decimal("0"):
        return None, "line {0}: {1} must be greater than 0 (got {2})".format(
            line_number, field_name, value
        )
    return value, None


def load_products(raw_rows, fieldnames):
    """Validate raw CSV rows and return a clean list of product dicts.

    raw_rows is a list of dict rows as produced by csv.DictReader. fieldnames is
    the header list. Every problem found is collected and raised together so the
    operator can fix the file in one pass.

    Returns a list of dicts: {"sku", "product_name", "unit_cost" (Decimal)}.
    """
    problems = []

    missing_columns = [c for c in REQUIRED_COLUMNS if c not in (fieldnames or [])]
    if missing_columns:
        raise ValidationError(
            ["missing required column(s): " + ", ".join(missing_columns)]
        )

    products = []
    seen_skus = set()
    for index, row in enumerate(raw_rows):
        # Header is line 1, so the first data row is line 2.
        line_number = index + 2
        row_ok = True

        sku = (row.get("sku") or "").strip()
        product_name = (row.get("product_name") or "").strip()

        if sku == "":
            problems.append("line {0}: sku is missing".format(line_number))
            row_ok = False
        elif sku in seen_skus:
            problems.append(
                "line {0}: duplicate sku '{1}'".format(line_number, sku)
            )
            row_ok = False
        else:
            seen_skus.add(sku)

        unit_cost, cost_error = _parse_positive_decimal(
            row.get("unit_cost"), "unit_cost", line_number
        )
        if cost_error:
            problems.append(cost_error)
            row_ok = False

        if row_ok:
            products.append(
                {"sku": sku, "product_name": product_name, "unit_cost": unit_cost}
            )

    if not raw_rows:
        problems.append("no product rows found (file has a header but no data)")

    if problems:
        raise ValidationError(problems)

    return products


def build_schedule(products, tiers=None):
    """Expand each product across every tier into schedule rows.

    Returns a list of dicts with Decimal values, one per (product, tier). The CLI
    formats these for the console and CSV.
    """
    if tiers is None:
        tiers = DEFAULT_TIERS

    schedule = []
    for product in products:
        for label, min_quantity, target_margin in tiers:
            price = compute_wholesale_price(product["unit_cost"], target_margin)
            achieved = compute_achieved_margin(price, product["unit_cost"])
            schedule.append(
                {
                    "sku": product["sku"],
                    "product_name": product["product_name"],
                    "unit_cost": product["unit_cost"],
                    "tier_label": label,
                    "min_quantity": min_quantity,
                    "target_margin": quantize_margin(target_margin),
                    "wholesale_price": price,
                    "achieved_margin": achieved,
                }
            )
    return schedule

"""Pure business logic for the product cost sensitivity simulator.

This module takes the approved pricing schedule from tool 1, applies a raw
material cost increase, holds each wholesale price constant, and reports the
resulting gross margin for every product and tier. It does no file reading and
no printing, so the rules are easy to test with fixed numbers.

All money and margin math uses decimal.Decimal with ROUND_HALF_UP.
"""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

MONEY = Decimal("0.01")
MARGIN = Decimal("0.0001")

# Columns the approved schedule (tool 1 output) must provide.
SCHEDULE_COLUMNS = ["sku", "tier_label", "unit_cost", "wholesale_price"]

# The company minimum acceptable gross margin, used as the bar when the caller
# does not supply one. Overridable from the command line.
DEFAULT_THRESHOLD = Decimal("0.33")

# Per-row outcomes after the increase is applied.
STATUS_OK = "OK"
STATUS_BELOW_THRESHOLD = "BELOW_THRESHOLD"
STATUS_ALREADY_BELOW = "ALREADY_BELOW"


class ValidationError(Exception):
    """Raised for problems that stop the whole run."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def quantize_money(value):
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def quantize_margin(value):
    return value.quantize(MARGIN, rounding=ROUND_HALF_UP)


def validate_increase(increase_pct):
    """A cost increase below -100 percent would push cost below zero."""
    if increase_pct <= Decimal("-100"):
        raise ValidationError(
            ["cost increase must be greater than -100 percent (got {0})".format(increase_pct)]
        )
    return increase_pct


def validate_threshold(threshold):
    if not (Decimal("0") <= threshold < Decimal("1")):
        raise ValidationError(
            ["threshold must be between 0 and 1 (got {0})".format(threshold)]
        )
    return threshold


def apply_increase(unit_cost, increase_pct):
    """Raise a cost by a percentage and round to the cent."""
    factor = Decimal("1") + (increase_pct / Decimal("100"))
    return quantize_money(unit_cost * factor)


def gross_margin(wholesale_price, unit_cost):
    """Gross margin fraction at a given price and cost, to 4 places."""
    if wholesale_price <= Decimal("0"):
        raise ValidationError(["wholesale price must be positive"])
    return quantize_margin((wholesale_price - unit_cost) / wholesale_price)


def status_for(old_margin, new_margin, threshold):
    """Classify a row. A product already under the bar before the increase is
    called out separately so it is not confused with a fresh crossing."""
    if old_margin < threshold:
        return STATUS_ALREADY_BELOW
    if new_margin < threshold:
        return STATUS_BELOW_THRESHOLD
    return STATUS_OK


def load_schedule(raw_rows, fieldnames):
    """Validate the approved schedule and return a list of product rows.

    Each row: sku, product_name, tier_label, unit_cost (Decimal),
    wholesale_price (Decimal).
    """
    missing = [c for c in SCHEDULE_COLUMNS if c not in (fieldnames or [])]
    if missing:
        raise ValidationError(
            ["pricing schedule missing required column(s): " + ", ".join(missing)]
        )

    products = []
    for index_position, row in enumerate(raw_rows):
        line = index_position + 2
        sku = (row.get("sku") or "").strip()
        if sku == "":
            raise ValidationError(["pricing schedule line {0}: sku is missing".format(line)])
        try:
            unit_cost = Decimal((row.get("unit_cost") or "").strip())
            wholesale_price = Decimal((row.get("wholesale_price") or "").strip())
        except InvalidOperation:
            raise ValidationError(
                ["pricing schedule line {0}: could not parse cost or price".format(line)]
            )
        products.append(
            {
                "sku": sku,
                "product_name": (row.get("product_name") or "").strip(),
                "tier_label": (row.get("tier_label") or "").strip(),
                "unit_cost": unit_cost,
                "wholesale_price": wholesale_price,
            }
        )

    if not products:
        raise ValidationError(["pricing schedule has no rows"])
    return products


def simulate(products, increase_pct, threshold=None):
    """Apply the increase to every product row and classify the result."""
    if threshold is None:
        threshold = DEFAULT_THRESHOLD
    validate_increase(increase_pct)
    validate_threshold(threshold)

    results = []
    for product in products:
        old_margin = gross_margin(product["wholesale_price"], product["unit_cost"])
        new_cost = apply_increase(product["unit_cost"], increase_pct)
        new_margin = gross_margin(product["wholesale_price"], new_cost)
        results.append(
            {
                "sku": product["sku"],
                "product_name": product["product_name"],
                "tier_label": product["tier_label"],
                "old_cost": product["unit_cost"],
                "new_cost": new_cost,
                "wholesale_price": product["wholesale_price"],
                "old_margin": old_margin,
                "new_margin": new_margin,
                "margin_delta": quantize_margin(new_margin - old_margin),
                "status": status_for(old_margin, new_margin, threshold),
            }
        )
    return results


def summarize(results):
    summary = {
        STATUS_OK: 0,
        STATUS_BELOW_THRESHOLD: 0,
        STATUS_ALREADY_BELOW: 0,
        "total": len(results),
    }
    for result in results:
        summary[result["status"]] = summary.get(result["status"], 0) + 1
    return summary

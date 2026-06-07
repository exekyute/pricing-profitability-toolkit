"""Pure business logic for the margin leakage audit.

This module reconciles a transaction ledger against the approved pricing
schedule produced by tool 1. It decides, per transaction, whether the sale
earned at least the approved gross margin for its volume tier. It does no file
reading and no printing, so the rules are easy to test with fixed numbers.

All money and margin math uses decimal.Decimal with ROUND_HALF_UP.
"""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

MONEY = Decimal("0.01")
MARGIN = Decimal("0.0001")

# Columns the ledger must provide.
LEDGER_COLUMNS = ["txn_id", "sku", "order_quantity", "unit_sale_price", "unit_cost"]

# Columns the approved schedule (tool 1 output) must provide.
SCHEDULE_COLUMNS = [
    "sku",
    "tier_label",
    "min_quantity",
    "target_margin",
    "wholesale_price",
]

# Per-transaction outcomes.
STATUS_OK = "OK"
STATUS_FLAGGED = "FLAGGED"
STATUS_UNKNOWN_SKU = "UNKNOWN_SKU"
STATUS_DUPLICATE = "DUPLICATE"
STATUS_ERROR = "ERROR"


class ValidationError(Exception):
    """Raised for file-level problems that stop the whole run."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def quantize_money(value):
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def quantize_margin(value):
    return value.quantize(MARGIN, rounding=ROUND_HALF_UP)


def _parse_decimal(raw, field_name, require_positive=True):
    text = (raw or "").strip()
    if text == "":
        return None, "{0} is missing".format(field_name)
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None, "{0} '{1}' is not a number".format(field_name, text)
    if require_positive and value <= Decimal("0"):
        return None, "{0} must be greater than 0 (got {1})".format(field_name, value)
    return value, None


def _parse_int(raw, field_name):
    text = (raw or "").strip()
    if text == "":
        return None, "{0} is missing".format(field_name)
    try:
        value = int(text)
    except ValueError:
        return None, "{0} '{1}' is not a whole number".format(field_name, text)
    if value <= 0:
        return None, "{0} must be greater than 0 (got {1})".format(field_name, value)
    return value, None


def load_schedule(raw_rows, fieldnames):
    """Index the approved schedule as sku -> tiers sorted by minimum quantity.

    Each tier is a dict: tier_label, min_quantity (int), target_margin (Decimal),
    wholesale_price (Decimal). Tiers are sorted descending by min_quantity so the
    applicable tier for an order quantity is the first one that fits.
    """
    missing = [c for c in SCHEDULE_COLUMNS if c not in (fieldnames or [])]
    if missing:
        raise ValidationError(
            ["pricing schedule missing required column(s): " + ", ".join(missing)]
        )

    index = {}
    for index_position, row in enumerate(raw_rows):
        line = index_position + 2
        sku = (row.get("sku") or "").strip()
        if sku == "":
            raise ValidationError(["pricing schedule line {0}: sku is missing".format(line)])
        try:
            tier = {
                "tier_label": (row.get("tier_label") or "").strip(),
                "min_quantity": int((row.get("min_quantity") or "").strip()),
                "target_margin": Decimal((row.get("target_margin") or "").strip()),
                "wholesale_price": Decimal((row.get("wholesale_price") or "").strip()),
            }
        except (ValueError, InvalidOperation):
            raise ValidationError(
                ["pricing schedule line {0}: could not parse tier values".format(line)]
            )
        index.setdefault(sku, []).append(tier)

    if not index:
        raise ValidationError(["pricing schedule has no rows"])

    for sku in index:
        index[sku].sort(key=lambda tier: tier["min_quantity"], reverse=True)
    return index


def determine_tier(tiers_for_sku, order_quantity):
    """Return the tier whose minimum quantity the order meets, else None."""
    for tier in tiers_for_sku:  # already sorted high to low
        if order_quantity >= tier["min_quantity"]:
            return tier
    return None


def audit_ledger(ledger_rows, ledger_fieldnames, schedule_index, threshold=None):
    """Audit every transaction and return a list of result dicts.

    A missing ledger column stops the run (ValidationError). Bad data inside a
    single row does not stop the run: that row is marked ERROR and the audit
    continues, because one bad record should not hide the rest of the ledger.
    """
    missing = [c for c in LEDGER_COLUMNS if c not in (ledger_fieldnames or [])]
    if missing:
        raise ValidationError(
            ["ledger missing required column(s): " + ", ".join(missing)]
        )

    results = []
    seen_txn_ids = set()

    for index_position, row in enumerate(ledger_rows):
        line = index_position + 2
        txn_id = (row.get("txn_id") or "").strip()
        sku = (row.get("sku") or "").strip()

        result = {
            "txn_id": txn_id,
            "sku": sku,
            "order_quantity": None,
            "unit_sale_price": None,
            "unit_cost": None,
            "tier_label": "",
            "target_margin": None,
            "actual_margin": None,
            "status": STATUS_OK,
            "leakage": Decimal("0.00"),
            "note": "",
        }

        if txn_id and txn_id in seen_txn_ids:
            result["status"] = STATUS_DUPLICATE
            result["note"] = "txn_id already seen earlier in the file"
            results.append(result)
            continue
        if txn_id:
            seen_txn_ids.add(txn_id)

        quantity, q_error = _parse_int(row.get("order_quantity"), "order_quantity")
        sale_price, s_error = _parse_decimal(row.get("unit_sale_price"), "unit_sale_price")
        unit_cost, c_error = _parse_decimal(row.get("unit_cost"), "unit_cost")
        row_errors = [e for e in (q_error, s_error, c_error) if e]
        if txn_id == "":
            row_errors.insert(0, "txn_id is missing")
        if row_errors:
            result["status"] = STATUS_ERROR
            result["note"] = "; ".join(row_errors)
            results.append(result)
            continue

        result["order_quantity"] = quantity
        result["unit_sale_price"] = sale_price
        result["unit_cost"] = unit_cost

        tiers = schedule_index.get(sku)
        if not tiers:
            result["status"] = STATUS_UNKNOWN_SKU
            result["note"] = "sku is not in the approved pricing schedule"
            results.append(result)
            continue

        tier = determine_tier(tiers, quantity)
        result["tier_label"] = tier["tier_label"]
        target = threshold if threshold is not None else tier["target_margin"]
        result["target_margin"] = quantize_margin(target)

        actual = quantize_margin((sale_price - unit_cost) / sale_price)
        result["actual_margin"] = actual

        if actual < target:
            result["status"] = STATUS_FLAGGED
            shortfall_per_unit = tier["wholesale_price"] - sale_price
            if shortfall_per_unit < Decimal("0"):
                shortfall_per_unit = Decimal("0")
            result["leakage"] = quantize_money(shortfall_per_unit * quantity)
            result["note"] = "margin below approved {0} target".format(tier["tier_label"])
        else:
            result["status"] = STATUS_OK

        results.append(result)

    return results


def summarize(results):
    """Roll the per-transaction results into counts and total leakage."""
    summary = {
        STATUS_OK: 0,
        STATUS_FLAGGED: 0,
        STATUS_UNKNOWN_SKU: 0,
        STATUS_DUPLICATE: 0,
        STATUS_ERROR: 0,
        "total": len(results),
        "total_leakage": Decimal("0.00"),
    }
    for result in results:
        summary[result["status"]] = summary.get(result["status"], 0) + 1
        summary["total_leakage"] += result["leakage"]
    summary["total_leakage"] = quantize_money(summary["total_leakage"])
    return summary

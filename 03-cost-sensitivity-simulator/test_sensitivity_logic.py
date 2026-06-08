"""Unit tests for the cost sensitivity simulator logic.

Every expected number was worked out by hand. The zero-increase test is the
proof of agreement with tool 1: with no change applied, the simulator reproduces
tool 1's achieved margin for SKU-1001 Tier 1 exactly, 40.00 percent. Run with:

    python -m unittest -v
"""

import unittest
from decimal import Decimal

from sensitivity_logic import (
    ValidationError,
    apply_increase,
    gross_margin,
    status_for,
    validate_increase,
    load_schedule,
    simulate,
    summarize,
    STATUS_OK,
    STATUS_BELOW_THRESHOLD,
    STATUS_ALREADY_BELOW,
)

HEADER = ["sku", "product_name", "tier_label", "unit_cost", "wholesale_price"]


def sample_products():
    rows = [
        {"sku": "SKU-1001", "product_name": "Aluminum Bracket", "tier_label": "Tier 1", "unit_cost": "12.00", "wholesale_price": "20.00"},
        {"sku": "SKU-1001", "product_name": "Aluminum Bracket", "tier_label": "Tier 2", "unit_cost": "12.00", "wholesale_price": "18.46"},
        {"sku": "SKU-1001", "product_name": "Aluminum Bracket", "tier_label": "Tier 3", "unit_cost": "12.00", "wholesale_price": "17.14"},
    ]
    return load_schedule(rows, HEADER)


class MathTests(unittest.TestCase):
    def test_apply_increase_rounds_to_cent(self):
        self.assertEqual(apply_increase(Decimal("12.00"), Decimal("8")), Decimal("12.96"))

    def test_apply_decrease(self):
        self.assertEqual(apply_increase(Decimal("12.00"), Decimal("-10")), Decimal("10.80"))

    def test_gross_margin(self):
        self.assertEqual(gross_margin(Decimal("20.00"), Decimal("12.96")), Decimal("0.3520"))
        self.assertEqual(gross_margin(Decimal("20.00"), Decimal("12.00")), Decimal("0.4000"))


class StatusTests(unittest.TestCase):
    def test_ok_when_both_above(self):
        self.assertEqual(status_for(Decimal("0.40"), Decimal("0.35"), Decimal("0.33")), STATUS_OK)

    def test_below_when_increase_crosses(self):
        self.assertEqual(status_for(Decimal("0.3499"), Decimal("0.2979"), Decimal("0.33")), STATUS_BELOW_THRESHOLD)

    def test_already_below_before_increase(self):
        self.assertEqual(status_for(Decimal("0.2999"), Decimal("0.2439"), Decimal("0.33")), STATUS_ALREADY_BELOW)


class ValidateTests(unittest.TestCase):
    def test_increase_at_or_below_minus_100_rejected(self):
        with self.assertRaises(ValidationError):
            validate_increase(Decimal("-150"))

    def test_missing_schedule_column_raises(self):
        with self.assertRaises(ValidationError):
            load_schedule([{"sku": "X", "unit_cost": "1.00"}], ["sku", "unit_cost"])


class SimulateTests(unittest.TestCase):
    def setUp(self):
        self.products = sample_products()

    def test_eight_percent_splits_three_ways(self):
        results = simulate(self.products, Decimal("8"), Decimal("0.33"))
        by_tier = {r["tier_label"]: r for r in results}
        # Tier 1 stays above the floor.
        self.assertEqual(by_tier["Tier 1"]["new_cost"], Decimal("12.96"))
        self.assertEqual(by_tier["Tier 1"]["new_margin"], Decimal("0.3520"))
        self.assertEqual(by_tier["Tier 1"]["margin_delta"], Decimal("-0.0480"))
        self.assertEqual(by_tier["Tier 1"]["status"], STATUS_OK)
        # Tier 2 crosses below after the increase.
        self.assertEqual(by_tier["Tier 2"]["new_margin"], Decimal("0.2979"))
        self.assertEqual(by_tier["Tier 2"]["status"], STATUS_BELOW_THRESHOLD)
        # Tier 3 was already below before the increase.
        self.assertEqual(by_tier["Tier 3"]["status"], STATUS_ALREADY_BELOW)

    def test_zero_increase_reproduces_tool_one(self):
        # No change applied: new margin equals the original achieved margin.
        # SKU-1001 Tier 1 reads 40.00 percent, matching tool 1 exactly.
        results = simulate(self.products, Decimal("0"), Decimal("0.33"))
        tier1 = next(r for r in results if r["tier_label"] == "Tier 1")
        self.assertEqual(tier1["new_cost"], tier1["old_cost"])
        self.assertEqual(tier1["new_margin"], Decimal("0.4000"))
        self.assertEqual(tier1["margin_delta"], Decimal("0.0000"))

    def test_summary_counts(self):
        summary = summarize(simulate(self.products, Decimal("8"), Decimal("0.33")))
        self.assertEqual(summary[STATUS_OK], 1)
        self.assertEqual(summary[STATUS_BELOW_THRESHOLD], 1)
        self.assertEqual(summary[STATUS_ALREADY_BELOW], 1)

    def test_bad_increase_rejected_through_simulate(self):
        with self.assertRaises(ValidationError):
            simulate(self.products, Decimal("-150"), Decimal("0.33"))


if __name__ == "__main__":
    unittest.main()

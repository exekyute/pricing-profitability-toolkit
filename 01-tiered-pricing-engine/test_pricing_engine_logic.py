"""Unit tests for the tiered pricing engine logic.

Every expected number here was worked out by hand so the tests double as a proof
that the rounding and margin rules behave as documented in spec.md. Run with:

    python -m unittest -v
"""

import unittest
from decimal import Decimal

from pricing_engine_logic import (
    ValidationError,
    compute_wholesale_price,
    compute_achieved_margin,
    load_products,
    build_schedule,
)


class WholesalePriceTests(unittest.TestCase):
    def test_clean_divide_gives_exact_price(self):
        # 12.00 / (1 - 0.40) = 20.00 exactly. This is the cross-tool anchor:
        # tool 2 audits a SKU-1001 sale at 20.00 and must read back 40.00%.
        price = compute_wholesale_price(Decimal("12.00"), Decimal("0.40"))
        self.assertEqual(price, Decimal("20.00"))

    def test_price_rounds_to_cents_half_up(self):
        # 10.00 / 0.60 = 16.6666... rounds up to 16.67.
        price = compute_wholesale_price(Decimal("10.00"), Decimal("0.40"))
        self.assertEqual(price, Decimal("16.67"))

    def test_margin_at_or_above_one_is_rejected(self):
        with self.assertRaises(ValidationError):
            compute_wholesale_price(Decimal("5.00"), Decimal("1.00"))


class AchievedMarginTests(unittest.TestCase):
    def test_exact_margin_when_price_is_clean(self):
        # (20.00 - 12.00) / 20.00 = 0.4000.
        achieved = compute_achieved_margin(Decimal("20.00"), Decimal("12.00"))
        self.assertEqual(achieved, Decimal("0.4000"))

    def test_rounding_nudges_achieved_off_target(self):
        # At cost 10.00 the rounded price 16.67 earns 0.4001, slightly above the
        # 0.40 target. Reporting this proves the schedule is internally honest.
        achieved = compute_achieved_margin(Decimal("16.67"), Decimal("10.00"))
        self.assertEqual(achieved, Decimal("0.4001"))


class LoadProductsTests(unittest.TestCase):
    HEADER = ["sku", "product_name", "unit_cost"]

    def test_clean_rows_load(self):
        rows = [
            {"sku": "SKU-1", "product_name": "A", "unit_cost": "5.00"},
            {"sku": "SKU-2", "product_name": "B", "unit_cost": "8.50"},
        ]
        products = load_products(rows, self.HEADER)
        self.assertEqual(len(products), 2)
        self.assertEqual(products[0]["unit_cost"], Decimal("5.00"))

    def test_missing_required_column_raises(self):
        rows = [{"sku": "SKU-1", "unit_cost": "5.00"}]
        with self.assertRaises(ValidationError):
            load_products(rows, ["sku", "unit_cost"])

    def test_empty_file_raises(self):
        with self.assertRaises(ValidationError):
            load_products([], self.HEADER)

    def test_every_bad_row_is_collected(self):
        rows = [
            {"sku": "SKU-A", "product_name": "ok", "unit_cost": "5.00"},
            {"sku": "SKU-B", "product_name": "zero", "unit_cost": "0.00"},
            {"sku": "SKU-C", "product_name": "neg", "unit_cost": "-4.00"},
            {"sku": "SKU-D", "product_name": "text", "unit_cost": "abc"},
            {"sku": "SKU-A", "product_name": "dup", "unit_cost": "9.00"},
            {"sku": "", "product_name": "nosku", "unit_cost": "3.00"},
            {"sku": "SKU-F", "product_name": "nocost", "unit_cost": ""},
        ]
        with self.assertRaises(ValidationError) as caught:
            load_products(rows, self.HEADER)
        # Six bad rows: zero, negative, non-numeric, duplicate, missing sku,
        # missing cost. The one good row is not a problem.
        self.assertEqual(len(caught.exception.problems), 6)


class BuildScheduleTests(unittest.TestCase):
    def test_three_rows_per_product(self):
        products = [{"sku": "SKU-1001", "product_name": "Bracket", "unit_cost": Decimal("12.00")}]
        schedule = build_schedule(products)
        self.assertEqual(len(schedule), 3)
        first = schedule[0]
        self.assertEqual(first["tier_label"], "Tier 1")
        self.assertEqual(first["wholesale_price"], Decimal("20.00"))
        self.assertEqual(first["achieved_margin"], Decimal("0.4000"))


if __name__ == "__main__":
    unittest.main()

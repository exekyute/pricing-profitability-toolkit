"""Unit tests for the margin leakage audit logic.

Every expected number was worked out by hand. The boundary test is the proof
that this tool agrees with tool 1: a sale of SKU-1001 at 20.00 earns exactly
40.00%, the same figure tool 1 set as the Tier 1 target. Run with:

    python -m unittest -v
"""

import unittest
from decimal import Decimal

from audit_logic import (
    ValidationError,
    load_schedule,
    determine_tier,
    audit_ledger,
    summarize,
    STATUS_OK,
    STATUS_FLAGGED,
    STATUS_UNKNOWN_SKU,
    STATUS_DUPLICATE,
    STATUS_ERROR,
)

SCHEDULE_HEADER = ["sku", "tier_label", "min_quantity", "target_margin", "wholesale_price"]
LEDGER_HEADER = ["txn_id", "sku", "order_quantity", "unit_sale_price", "unit_cost"]


def sample_schedule():
    rows = [
        {"sku": "SKU-1001", "tier_label": "Tier 1", "min_quantity": "1", "target_margin": "0.4000", "wholesale_price": "20.00"},
        {"sku": "SKU-1001", "tier_label": "Tier 2", "min_quantity": "100", "target_margin": "0.3500", "wholesale_price": "18.46"},
        {"sku": "SKU-1001", "tier_label": "Tier 3", "min_quantity": "500", "target_margin": "0.3000", "wholesale_price": "17.14"},
        {"sku": "SKU-1002", "tier_label": "Tier 1", "min_quantity": "1", "target_margin": "0.4000", "wholesale_price": "16.67"},
    ]
    return load_schedule(rows, SCHEDULE_HEADER)


class ScheduleTests(unittest.TestCase):
    def test_missing_column_raises(self):
        with self.assertRaises(ValidationError):
            load_schedule([{"sku": "X"}], ["sku"])

    def test_tier_selected_by_quantity(self):
        index = sample_schedule()
        tiers = index["SKU-1001"]
        self.assertEqual(determine_tier(tiers, 10)["tier_label"], "Tier 1")
        self.assertEqual(determine_tier(tiers, 150)["tier_label"], "Tier 2")
        self.assertEqual(determine_tier(tiers, 600)["tier_label"], "Tier 3")


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.index = sample_schedule()

    def _audit(self, rows, threshold=None):
        return audit_ledger(rows, LEDGER_HEADER, self.index, threshold)

    def test_boundary_sale_is_not_flagged(self):
        # SKU-1001 at 20.00 earns (20-12)/20 = 0.4000, exactly the Tier 1 target.
        # This is the cross-tool agreement value with tool 1.
        rows = [{"txn_id": "T1", "sku": "SKU-1001", "order_quantity": "10", "unit_sale_price": "20.00", "unit_cost": "12.00"}]
        result = self._audit(rows)[0]
        self.assertEqual(result["actual_margin"], Decimal("0.4000"))
        self.assertEqual(result["status"], STATUS_OK)

    def test_below_target_is_flagged_with_leakage(self):
        # SKU-1001 at 19.00 earns (19-12)/19 = 0.3684, below the 0.40 target.
        # Leakage = (20.00 - 19.00) * 50 = 50.00.
        rows = [{"txn_id": "T2", "sku": "SKU-1001", "order_quantity": "50", "unit_sale_price": "19.00", "unit_cost": "12.00"}]
        result = self._audit(rows)[0]
        self.assertEqual(result["actual_margin"], Decimal("0.3684"))
        self.assertEqual(result["status"], STATUS_FLAGGED)
        self.assertEqual(result["leakage"], Decimal("50.00"))

    def test_unknown_sku(self):
        rows = [{"txn_id": "T3", "sku": "SKU-9999", "order_quantity": "10", "unit_sale_price": "50.00", "unit_cost": "30.00"}]
        self.assertEqual(self._audit(rows)[0]["status"], STATUS_UNKNOWN_SKU)

    def test_duplicate_txn_id(self):
        rows = [
            {"txn_id": "T4", "sku": "SKU-1002", "order_quantity": "5", "unit_sale_price": "16.67", "unit_cost": "10.00"},
            {"txn_id": "T4", "sku": "SKU-1002", "order_quantity": "5", "unit_sale_price": "16.67", "unit_cost": "10.00"},
        ]
        results = self._audit(rows)
        self.assertEqual(results[1]["status"], STATUS_DUPLICATE)

    def test_bad_row_becomes_error_not_crash(self):
        rows = [{"txn_id": "T5", "sku": "SKU-1002", "order_quantity": "5", "unit_sale_price": "0.00", "unit_cost": "0.85"}]
        result = self._audit(rows)[0]
        self.assertEqual(result["status"], STATUS_ERROR)

    def test_missing_ledger_column_raises(self):
        with self.assertRaises(ValidationError):
            audit_ledger([{"txn_id": "T6"}], ["txn_id"], self.index)

    def test_threshold_override_changes_outcome(self):
        # At the 0.40 Tier 1 target this sale (0.3684) is flagged. Lower the bar
        # to 0.30 and the same sale passes.
        rows = [{"txn_id": "T7", "sku": "SKU-1001", "order_quantity": "50", "unit_sale_price": "19.00", "unit_cost": "12.00"}]
        self.assertEqual(self._audit(rows, threshold=Decimal("0.30"))[0]["status"], STATUS_OK)

    def test_summary_counts_and_total_leakage(self):
        rows = [
            {"txn_id": "A", "sku": "SKU-1001", "order_quantity": "10", "unit_sale_price": "20.00", "unit_cost": "12.00"},
            {"txn_id": "B", "sku": "SKU-1001", "order_quantity": "50", "unit_sale_price": "19.00", "unit_cost": "12.00"},
            {"txn_id": "C", "sku": "SKU-1002", "order_quantity": "5", "unit_sale_price": "14.00", "unit_cost": "10.00"},
        ]
        summary = summarize(self._audit(rows))
        self.assertEqual(summary[STATUS_OK], 1)
        self.assertEqual(summary[STATUS_FLAGGED], 2)
        # 50.00 from B plus (16.67 - 14.00) * 5 = 13.35 from C = 63.35.
        self.assertEqual(summary["total_leakage"], Decimal("63.35"))


if __name__ == "__main__":
    unittest.main()

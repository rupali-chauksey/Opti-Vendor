import unittest
from engine import (
    esc,
    compute_health_status,
    compute_reorder_qty,
    check_approval_required,
    score_vendor_candidate,
    negotiate_a2a_round,
    get_product_policy
)

class TestEngine(unittest.TestCase):

    def test_latex_escape_helper(self):
        self.assertEqual(esc("$500.00"), "\\$500.00")
        self.assertEqual(esc("Total: $100"), "Total: \\$100")
        self.assertEqual(esc(None), "")

    def test_health_status_engine(self):
        # Stock = 0 -> CRITICAL_STOCKOUT
        self.assertEqual(compute_health_status(0, 100, 15.0), "CRITICAL_STOCKOUT")
        
        # Days of supply < 2.0 -> CRITICAL_STOCKOUT
        self.assertEqual(compute_health_status(12, 100, 15.0), "CRITICAL_STOCKOUT") # 0.8 days
        
        # Shrimp (5/25, velocity=1) -> LOW_STOCK because stock <= 0.5 * target
        self.assertEqual(compute_health_status(5, 25, 1.0), "LOW_STOCK")
        
        # Pepperoni (40/80, velocity=8) -> LOW_STOCK because stock <= 0.5 * target
        self.assertEqual(compute_health_status(40, 80, 8.0), "LOW_STOCK")
        
        # Healthy stock level -> OPTIMAL
        self.assertEqual(compute_health_status(90, 100, 5.0), "OPTIMAL")

    def test_reorder_qty_engine(self):
        # Target=100, Stock=12, Velocity=15, Lead Time=2 -> Needed: (100 - 12) + (15 * 2) = 118
        self.assertEqual(compute_reorder_qty(12, 100, 15.0, lead_time=2.0), 118)
        
        # Stock >= target + lead time consumption -> 0
        self.assertEqual(compute_reorder_qty(100, 100, 0.0), 0)

    def test_approval_check_threshold(self):
        # Exactly $500 -> False
        self.assertFalse(check_approval_required(500.0))
        
        # $500.01 -> True
        self.assertTrue(check_approval_required(500.01))
        
        # $277.20 -> False
        self.assertFalse(check_approval_required(277.20))
        
        # $8280.00 -> True
        self.assertTrue(check_approval_required(8280.00))

    def test_price_ceiling_policy_enforcement(self):
        # Price exceeding product max unit price ceiling -> Disqualified
        score, status, _ = score_vendor_candidate(
            price=15.00,
            list_price=15.00,
            reliability=0.95,
            delivery_days=2,
            max_unit_price=10.00 # Ceiling is $10.00
        )
        self.assertEqual(score, 0.0)
        self.assertIn("DISQUALIFIED", status)

    def test_a2a_multi_round_negotiation(self):
        offer = {"price_wholesale": 10.0}
        
        # Round 1
        r1 = negotiate_a2a_round(offer, quantity=100, round_num=1)
        self.assertEqual(r1["negotiated_price"], 9.0) # 10% discount for qty >= 50
        
        # Round 2
        r2 = negotiate_a2a_round(offer, quantity=100, round_num=2)
        self.assertEqual(r2["negotiated_price"], 8.5) # 15% discount counter

if __name__ == "__main__":
    unittest.main()

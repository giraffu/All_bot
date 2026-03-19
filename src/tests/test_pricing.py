import unittest
from decimal import Decimal
from src.database.models import User, MembershipPlan, DiscountRule
from src.api.pricing_engine import PricingEngine

class TestPricingEngine(unittest.TestCase):
    def setUp(self):
        self.plan_basic = MembershipPlan(
            id=1, name="基础月卡", identity_name="内门弟子", price_ton=Decimal("1.99"), reward_credits=400
        )
        self.plan_pro = MembershipPlan(
            id=2, name="高级月卡", identity_name="核心弟子", price_ton=Decimal("4.99"), reward_credits=1200
        )
        
        self.rules = [
            DiscountRule(rule_type="FIRST_CHARGE", target_level=None, discount_rate=Decimal("0.50")),
            DiscountRule(rule_type="LEVEL_DISCOUNT", target_level="化神期", discount_rate=Decimal("0.85")),
            DiscountRule(rule_type="LEVEL_DISCOUNT", target_level="大乘期", discount_rate=Decimal("0.80"))
        ]

    def test_first_charge_discount(self):
        user = User(id=1, user_group="凡人", is_first_charge=True)
        result = PricingEngine.calculate_final_price(user, self.plan_basic, self.rules)
        
        self.assertEqual(result["original_price"], Decimal("1.99"))
        self.assertEqual(result["final_price"], Decimal("1.00")) # 1.99 * 0.5 = 0.995 -> 1.00
        self.assertIn("First Charge: 0.50", result["applied_rules"])

    def test_level_discount_only(self):
        user = User(id=2, user_group="化神期", is_first_charge=False)
        result = PricingEngine.calculate_final_price(user, self.plan_pro, self.rules)
        
        self.assertEqual(result["original_price"], Decimal("4.99"))
        # 4.99 * 0.85 = 4.2415 -> 4.24
        self.assertEqual(result["final_price"], Decimal("4.24"))
        self.assertIn("Level Discount (化神期): 0.85", result["applied_rules"])

    def test_combined_discount(self):
        user = User(id=3, user_group="大乘期", is_first_charge=True)
        result = PricingEngine.calculate_final_price(user, self.plan_pro, self.rules)
        
        self.assertEqual(result["original_price"], Decimal("4.99"))
        # 4.99 * 0.80 * 0.50 = 1.996 -> 2.00
        self.assertEqual(result["final_price"], Decimal("2.00"))
        self.assertEqual(len(result["applied_rules"]), 2)

    def test_no_discount(self):
        user = User(id=4, user_group="练气期", is_first_charge=False)
        result = PricingEngine.calculate_final_price(user, self.plan_basic, self.rules)
        
        self.assertEqual(result["original_price"], Decimal("1.99"))
        self.assertEqual(result["final_price"], Decimal("1.99"))
        self.assertEqual(len(result["applied_rules"]), 0)

if __name__ == '__main__':
    unittest.main()

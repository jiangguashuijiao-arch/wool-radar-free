import unittest
from unittest.mock import patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cash_audit


class CashQualificationTests(unittest.TestCase):
    def test_actual_cash_terms_not_mistaken_for_auto_earning(self):
        text = "金币每日自动兑换成现金，可提现到支付宝，禁止使用模拟器、插件"
        result = cash_audit.assess(text, "示例")
        self.assertTrue(result["official_cash_claim"])
        self.assertTrue(result["platform_anti_cheat_clause"])
        self.assertFalse(result["automation_authorized"])
        self.assertFalse(result["verified_withdrawal"])
        self.assertFalse(result["fully_verified"])

    def test_membership_points_not_cash(self):
        result = cash_audit.assess("每日签到领取会员积分，可兑换优惠券", "示例")
        self.assertFalse(result["official_cash_claim"])
        self.assertFalse(result["fully_verified"])

    def test_no_account_no_withdrawal_evidence(self):
        result = cash_audit.assess("自动签到获得红包，可提现到支付宝", "示例")
        self.assertFalse(result["fully_verified"])
        self.assertFalse(result["verified_withdrawal"])

    def test_html_extraction(self):
        parser = cash_audit.TextExtractor()
        parser.feed("<style>fake</style><div>提现到支付宝</div><script>not valid</script>")
        self.assertIn("提现到支付宝", parser.text())
        self.assertNotIn("fake", parser.text())
        self.assertNotIn("not valid", parser.text())


if __name__ == "__main__":
    unittest.main()

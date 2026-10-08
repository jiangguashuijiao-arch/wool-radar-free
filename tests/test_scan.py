import json
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan


class ScannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample = json.loads((Path(__file__).parent / "sample.json").read_text(encoding="utf8"))

    def test_nested_payload(self):
        got = scan.normalize(self.sample["最新"], "最新")
        self.assertEqual(len(got), 3)
        self.assertEqual(got[0]["url"], "https://new.ixbk.net/post/123")

    def test_allowed_zero_cost_reward(self):
        self.assertTrue(scan.candidate(scan.normalize(self.sample["最新"], "最新")[0]))

    def test_recharge_and_invite_excluded(self):
        self.assertFalse(scan.candidate(scan.normalize(self.sample["最新"], "最新")[1]))
        self.assertFalse(scan.candidate(scan.normalize(self.sample["新赚吧"], "新赚吧")[0]))

    def test_under_one_yuan_excluded(self):
        self.assertFalse(scan.candidate(scan.normalize(self.sample["最新"], "最新")[2]))

    def test_no_amount_excluded(self):
        self.assertFalse(scan.candidate(scan.normalize(self.sample["值得买"], "值得买")[0]))

    def test_valid_free_money(self):
        self.assertTrue(scan.candidate(scan.normalize(self.sample["值得买"], "值得买")[1]))

    def test_external_url_rejected(self):
        self.assertIsNone(scan.safe_url("https://evil.example/phishing"))
        self.assertIsNone(scan.safe_url("javascript:alert(1)"))
        self.assertIsNone(scan.safe_url("https://new.ixbk.net.evil.example/post"))

    def test_markdown_sanitizing(self):
        self.assertNotIn("[", scan.markdown_escape("[test] | x"))

    def test_non_records_ignored(self):
        self.assertEqual(scan.normalize({"data": [{"title": "x"}]}, "最新"), [])


if __name__ == "__main__":
    unittest.main()

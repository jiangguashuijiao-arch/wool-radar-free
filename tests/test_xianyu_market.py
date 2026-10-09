import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import xianyu_market


def sample(i, price=100, *, sku="罗技 M720 旗舰版", date_value=None,
           condition="new_sealed", status="listed", url=None):
    return {
        "sku": sku,
        "asking_price": price,
        "condition": condition,
        "status": status,
        "observed_on": date_value or date.today().isoformat(),
        "listing_url": url or f"https://www.goofish.com/item?id={i}",
    }


class MarketPriceTests(unittest.TestCase):
    def test_no_crawling_or_sales_derived_from_listings(self):
        report = "\n".join(xianyu_market.markdown_section(Path("/not-a-real-file.json")))
        self.assertIn("不是成交价", report)
        self.assertIn("尚未提供价格样本", report)

    def test_five_unique_recent_asking_prices(self):
        prices = [95, 100, 110, 115, 120]
        rows = [sample(i, p) for i, p in enumerate(prices)]
        results, invalid = xianyu_market.summarize(rows)
        self.assertEqual(invalid, 0)
        self.assertTrue(results["罗技 M720 旗舰版"]["sufficient"])
        self.assertEqual(results["罗技 M720 旗舰版"]["median_asking"], 110.0)
        self.assertEqual(results["罗技 M720 旗舰版"]["lower_quartile_asking"], 100.0)

    def test_one_listing_never_counted_five_times(self):
        rows = [sample(1, p) for p in [100, 110, 120, 130, 140]]
        results, _ = xianyu_market.summarize(rows)
        self.assertEqual(results["罗技 M720 旗舰版"]["sample_count"], 1)
        self.assertFalse(results["罗技 M720 旗舰版"]["sufficient"])

    def test_mismatched_conditions_sold_and_outdated_excluded(self):
        rows = [
            sample(1, 111, status="sold"),
            sample(2, 112, condition="used"),
            sample(3, 115, date_value=(date.today() - timedelta(days=9)).isoformat()),
            sample(4, 120, url="https://goofish.com.evil.test/item/4"),
            sample(5, 130, url="http://www.goofish.com/item?id=5"),
            sample(6, 150, status="listed"),
        ]
        stats, rejected = xianyu_market.summarize(rows)
        self.assertEqual(rejected, 5)
        self.assertEqual(stats["罗技 M720 旗舰版"]["sample_count"], 1)

    def test_trim_extreme_price_but_not_pretend_sale(self):
        prices = [95, 100, 102, 104, 108, 999]
        stats, _ = xianyu_market.summarize([sample(i, p) for i, p in enumerate(prices)])
        item = stats["罗技 M720 旗舰版"]
        self.assertEqual(item["sample_count_after_iqr"], 5)
        self.assertEqual(item["median_asking"], 102.0)

    def test_fewer_than_five_raises_no_market_confidence(self):
        rows = [sample(1, 110), sample(2, 115)]
        results, _ = xianyu_market.summarize(rows)
        self.assertFalse(results["罗技 M720 旗舰版"]["sufficient"])
        self.assertNotIn("median_asking", results["罗技 M720 旗舰版"])

    def test_report_reads_local_json_and_labels_asking(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "listings.json"
            samples = [sample(i, p) for i, p in enumerate([95, 100, 102, 104, 108])]
            import json
            path.write_text(json.dumps(samples, ensure_ascii=False), encoding="utf-8")
            output = "\n".join(xianyu_market.markdown_section(path))
            self.assertIn("挂牌中位数", output)
            self.assertIn("¥102.00", output)
            self.assertIn("不是成交价", output)

    def test_forged_sales_do_not_count(self):
        row = sample(1, 100)
        row["status"] = "sold"
        row["paid_price"] = 180
        stats, rejected = xianyu_market.summarize([row])
        self.assertEqual(stats, {})
        self.assertEqual(rejected, 1)

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(ValueError):
            xianyu_market.summarize({"foo": 1})
        self.assertIsNone(xianyu_market.parse_record(sample(1, float("nan"))))


if __name__ == "__main__":
    unittest.main()

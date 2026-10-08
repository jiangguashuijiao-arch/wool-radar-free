import unittest
from datetime import date, datetime
from email.utils import format_datetime
from zoneinfo import ZoneInfo

import arbitrage


class ArbitrageTests(unittest.TestCase):
    def test_price_with_explicit_yuan(self):
        self.assertEqual(arbitrage.extract_price("致态TiPlus7100 1TB SSD 到手价 299元"), 299.0)
        self.assertIsNone(arbitrage.extract_price("SSD 固态硬盘 国补 299元"))
        self.assertIsNone(arbitrage.extract_price("SSD 满减后 到手299"))

    def test_categories_and_risks(self):
        self.assertEqual(arbitrage.category("WD SN580 1TB SSD 299元"), "SSD固态硬盘")
        self.assertIsNone(arbitrage.category("速溶咖啡 29元"))
        self.assertIsNone(arbitrage.normalize("512GB 拆机SSD 59元", "https://www.smzdm.com/p/11", "fixture"))

    def test_only_safe_deal_url(self):
        self.assertIsNone(arbitrage.safe_link("https://smzdm.com.evil.test/p/11"))
        self.assertEqual(arbitrage.safe_link("http://www.smzdm.com/p/11"), "https://www.smzdm.com/p/11")
        self.assertEqual(arbitrage.safe_link("https://www.smzdm.com/p/11"), "https://www.smzdm.com/p/11")

    def test_net_profit_conservative(self):
        offer = {"title": "SSD 299元", "purchase_price": 299}
        b = dict(confirmed_sale_price=390, outbound_shipping=10, risk_reserve=15,
                 inbound_shipping=0, platform_fee_rate=0.016)
        result = arbitrage.profit(offer, b)
        self.assertEqual(result["net"], 59.76)
        self.assertTrue(result["qualified"])

    def test_margin_under_cutoff(self):
        offer = {"purchase_price": 300}
        b = dict(confirmed_sale_price=340, outbound_shipping=10, risk_reserve=15)
        self.assertFalse(arbitrage.profit(offer, b)["qualified"])

    def test_evidence_must_be_fresh_and_same_condition(self):
        offer = {"title": "西数 WD SN580 1TB SSD 到手299元", "purchase_price": 299}
        b = {"sku_terms": ["SN580", "1TB"], "condition": "new_sealed",
             "checked_on": date.today().isoformat(), "confirmed_sale_price": 390,
             "sale_evidence_url": "https://www.goofish.com/item?id=123"}
        self.assertIsNotNone(arbitrage.match_benchmark(offer, [b]))
        self.assertIsNone(arbitrage.match_benchmark(offer, [{**b, "condition": "used"}]))
        self.assertIsNone(arbitrage.match_benchmark(offer, [{**b, "checked_on": "2024-01-01"}]))
        self.assertIsNone(arbitrage.match_benchmark(offer, [{**b, "sku_terms": ["SN770", "1TB"]}]))

    def test_no_benchmark_no_false_profit(self):
        offer = arbitrage.normalize("致态 1TB SSD 到手价299元", "https://www.smzdm.com/p/1234", "测试")
        doc, count = arbitrage.report([offer], [], [])
        self.assertEqual(count, 0)
        self.assertIn("待核实", doc)
        self.assertNotIn("试算净利¥", doc)

    def test_official_api_signature_format(self):
        params = arbitrage.signed_params({"app_key": "123", "timestamp": "111"}, "private")
        self.assertEqual(len(params["sign"]), 32)
        self.assertEqual(params["sign"], params["sign"].upper())

    def test_rss_recent_with_real_timestamp(self):
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        xml = ('<rss><channel><item><title>WD SN580 1TB SSD 到手价 299元</title>'
               '<link>https://www.smzdm.com/p/42</link><pubDate>' +
               format_datetime(now) + '</pubDate></item></channel></rss>')
        r = arbitrage.rss_items(xml, "RSS", now=now)
        self.assertEqual(len(r), 1)

    def test_api_prices_without_title_amount(self):
        sample = {"data": {"list": [{
            "article_title": "西部数据 WD SN580 1TB SSD 固态硬盘",
            "article_subtitle": "到手价格 299元",
            "digital_price": "299",
            "article_url": "http://www.smzdm.com/p/99999"
        }]}}
        result = arbitrage.api_items(sample)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["purchase_price"], 299)
        self.assertTrue(result[0]["url"].startswith("https://"))

    def test_api_excludes_subtitle_promo(self):
        sample = {"data": {"list": [{
            "article_title": "西部数据 WD SN580 1TB SSD 固态硬盘",
            "article_subtitle": "国补后到手299元",
            "digital_price": "299",
            "article_url": "https://www.smzdm.com/p/99999"
        }]}}
        self.assertEqual(arbitrage.api_items(sample), [])

    def test_api_items(self):
        sample = {"data":{"list":[{"article_title":"WD SN580 1TB SSD 到手价299元",
                 "article_url":"https://www.smzdm.com/p/3", "digital_price":"299"}]}}
        self.assertEqual(len(arbitrage.api_items(sample)), 1)


if __name__ == "__main__":
    unittest.main()

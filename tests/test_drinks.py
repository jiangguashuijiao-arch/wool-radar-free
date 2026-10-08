import json
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import drinks

class DrinksTests(unittest.TestCase):
    def test_free_drink_match_without_amount(self):
        item = dict(title="蜜雪冰城10月免单券免费抽", content="", id="1", url="https://new.ixbk.net/a", source="test")
        self.assertIsNotNone(drinks.classify(item, date(2026, 10, 9)))

    def test_one_cent_match(self):
        item = dict(title="霸王茶姬0.01元兑换券抢购", content="", id="1", url="https://new.ixbk.net/a", source="test")
        self.assertIsNotNone(drinks.classify(item, date(2026, 10, 9)))

    def test_regular_discount_excluded(self):
        item = dict(title="古茗9折优惠", content="", id="1", url="https://new.ixbk.net/a", source="test")
        self.assertIsNone(drinks.classify(item, date(2026, 10, 9)))

    def test_must_pay_excluded(self):
        item = dict(title="库迪咖啡先付款后抽免单", content="先付款活动", id="1", url="https://new.ixbk.net/a", source="test")
        self.assertIsNone(drinks.classify(item, date(2026, 10, 9)))

    def test_expired_range_excluded(self):
        item = dict(title="瑞幸咖啡0元券活动", content="活动时间9月28日至10月4日", id="1", url="https://new.ixbk.net/a", source="test")
        self.assertIsNone(drinks.classify(item, date(2026, 10, 9)))

    def test_active_range(self):
        self.assertFalse(drinks.expired_by_text("10月1日至10月31日", date(2026, 10, 9)))
        self.assertTrue(drinks.expired_by_text("10月1日至10月31日", date(2026, 11, 1)))

    def test_url_allowlist(self):
        self.assertIsNone(drinks.safe_href("http://example.com/a"))
        self.assertIsNone(drinks.safe_href("https://evil.test/phish"))
        self.assertEqual(drinks.safe_href("https://news.google.com/rss/a"), "https://news.google.com/rss/a")

    def test_news_rss_pubdate(self):
        rss = '''<rss version="2.0"><channel><item>
<title>蜜雪冰城免费喝奶茶</title>
<link>https://news.google.com/rss/articles/abc</link>
<description>免单券</description>
<pubDate>Fri, 09 Oct 2026 00:00:00 GMT</pubDate>
</item></channel></rss>'''
        result = drinks.normalize_news(rss, "RSS", datetime(2026, 10, 9, 8, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["published"], "2026-10-09")

    def test_campaign_dates(self):
        on_ninth = drinks.load_campaigns(date(2026, 10, 9))
        on_november = drinks.load_campaigns(date(2026, 11, 1))
        self.assertGreaterEqual(len(on_ninth), 1)
        self.assertEqual(len(on_november), 0)

    def test_report_disclaims_verified(self):
        text = drinks.make_report([], [], 10, [], False)
        self.assertIn("不验证库存", text)
        self.assertIn("不自动下单", text)

if __name__ == "__main__":
    unittest.main()

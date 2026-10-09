#!/usr/bin/env python3
"""SMZDM -> 闲鱼套利候选雷达。

只读官方好价 API（需合法申请的 AppKey/Secret）或官方公共 RSS。
没有可信的闲鱼成交价格证明，绝不把差价叫做已验证利润。
不登录闲鱼、不发布商品、不代买商品。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import scan
from scan import clean, markdown_escape

CHINA = ZoneInfo("Asia/Shanghai")
RSS = ("https://feed.smzdm.com", "https://fx.smzdm.com/feed", "https://feed.feedsky.com/smzdm")
PUBLIC_FEEDS = (("线报酷最新", "/plus/json/push.json"), ("线报酷赚客吧", "/plus/json/push_16.json"), ("线报酷新赚吧", "/plus/json/push_18.json"))
API = "https://openapi.smzdm.com/v1/youhui/list/show"
REPORT = Path("reports/arbitrage-latest.md")
WATCHLIST = Path("data/resale-benchmarks.json")
STATE = Path("data/arbitrage-seen.json")

# 首批类别：体积小、SKU 相对标准化。手机、存储卡、虚拟商品等风险较大，不自动入围。
CATEGORIES = {
    # 新的小件方向：轻、体积小、尽可能无电池、完整规格易核对。
    "手动维修工具": ("精密螺丝刀", "螺丝刀套装", "棘轮螺丝刀", "批头套装", "内六角",
                   "六角扳手", "套筒套装", "套筒组套", "工具组套", "工具套装",
                   "钢卷尺", "游标卡尺", "棘轮扳手", "工具钳"),
    "小件收纳配件": ("工具收纳盒", "数据线收纳包", "电子配件收纳盒", "防潮盒", "收纳工具箱"),
    "SSD固态硬盘": ("SSD", "固态硬盘", "SN770", "SN580", "NM790", "T500"),
    "内存条": ("DDR4", "DDR5", "内存条", "笔记本内存", "台式机内存"),
    "外设": ("鼠标", "机械键盘", "键盘", "游戏手柄", "游戏耳机"),
    "家用工具": ("电动螺丝刀", "锂电钻", "起子机", "充电式电钻"),
}
EXCLUSIONS = ("二手", "拆机", "维修", "扩容", "刷机", "故障", "官换", "无保",
              "以旧换新", "国补", "省补", "学生价", "专属", "邀请",
              "抽奖", "凑单", "多件起", "需买", "起购", "满减",
              "定金", "预售", "首单", "签到", "赠券", "盲盒", "福袋",
              "购买会员", "开通会员", "会员后", "需会员", "首充", "充值", "续费")
PRICE_PATTERNS = (
    re.compile(r"(?:券后|实付|到手|折后|特价|好价)[^\d]{0,5}(\d+(?:\.\d{1,2})?)\s*元"),
    re.compile(r"(\d+(?:\.\d{1,2})?)\s*元"),
)
MIN_NET_PROFIT = 30.0
MIN_NET_MARGIN = 0.18
# 小件优先只是排序，而非盈利或正品保证；进货价暂偏向¥25–¥300。
SMALL_BUY_MIN = 25.0
SMALL_BUY_MAX = 300.0
PRIORITY_CATEGORIES = {"手动维修工具", "小件收纳配件"}


def trial_minimum_sale_price(buy, fee_rate=0.016, outbound_shipping=8.0,
                             risk_reserve=10.0):
    """达到净利30元和净ROI18%所需最低售价；不是闲鱼成交价。"""
    import math
    price = float(buy)
    if price <= 0 or fee_rate < 0 or fee_rate >= 1:
        raise ValueError("价格或费率不合理")
    needed_profit = max(MIN_NET_PROFIT, price * MIN_NET_MARGIN)
    return math.ceil((price + outbound_shipping + risk_reserve + needed_profit)
                     / (1 - fee_rate) * 100 - 1e-9) / 100.0


def candidate_priority(offer):
    price = offer["purchase_price"]
    preferred = offer["category"] in PRIORITY_CATEGORIES
    affordable = SMALL_BUY_MIN <= price <= SMALL_BUY_MAX
    return (not (preferred and affordable), not affordable,
            abs(price - 90), offer["title"])


def scrape_text(value):
    return clean(value or "")


def category(title):
    text = title.upper()
    for label, keys in CATEGORIES.items():
        if any(key.upper() in text for key in keys):
            return label
    return None


def safe_link(raw):
    if not isinstance(raw, str):
        return None
    parsed = urllib.parse.urlparse(raw.strip())
    if parsed.scheme not in ("https", "http") or parsed.username or parsed.password:
        return None
    if parsed.hostname not in ("www.smzdm.com", "m.smzdm.com", "post.smzdm.com",
                               "faxian.smzdm.com", "news.smzdm.com", "go.smzdm.com",
                               "new.ixbk.net", "new.xianbao.fun"):
        return None
    return urllib.parse.urlunparse(parsed._replace(scheme="https"))


def extract_price(title):
    """只信任明确带'元'的标题，拒绝模糊、价格区间、多件活动。"""
    if any(word in title for word in EXCLUSIONS):
        return None
    if re.search(r"\d+\s*(?:件|套|个|包)\s*(?:共|到手|起)", title):
        return None
    for p in PRICE_PATTERNS:
        m = p.search(title)
        if m:
            price = float(m.group(1))
            return round(price, 2) if 10 <= price <= 5000 else None
    return None


def normalize(title, url, source, pubdate=None, price_override=None):
    title, url = scrape_text(title)[:180], safe_link(url)
    if not title or not url or category(title) is None:
        return None
    if any(w in title for w in EXCLUSIONS):
        return None
    try:
        price = round(float(price_override), 2) if price_override is not None else extract_price(title)
    except (ValueError, TypeError):
        return None
    if price is None or not (10 <= price <= 5000):
        return None
    if pubdate is not None:
        now = datetime.now(CHINA)
        if pubdate.tzinfo is None or pubdate > now + timedelta(hours=2) or pubdate < now - timedelta(hours=48):
            return None
    return {"id": hashlib.sha256(url.encode()).hexdigest()[:20], "title": title,
            "url": url, "source": source, "purchase_price": price,
            "category": category(title)}


def rss_items(payload, source, now=None):
    root = ET.fromstring(payload)
    now = now or datetime.now(CHINA)
    items = []
    for item in root.findall(".//item")[:120]:
        title, link = item.findtext("title"), item.findtext("link")
        stamp = item.findtext("pubDate")
        if not stamp:  # 没有发布日期就无法排除旧活动
            continue
        try:
            published = parsedate_to_datetime(stamp).astimezone(CHINA)
        except (ValueError, TypeError, OverflowError):
            continue
        # RSS 标题可能含标准中文商品名和金额，描述/正文不作为价格依据。
        result = normalize(title, link, source, published)
        if result and published <= now + timedelta(hours=2) and published >= now - timedelta(hours=48):
            items.append(result)
    return items


def signed_params(args, secret):
    params = {k: str(v) for k, v in args.items() if v is not None and str(v) != ""}
    joined = "".join(k + params[k] for k in sorted(params))
    digest = hashlib.md5((secret + joined + secret).encode("utf-8")).hexdigest().upper()
    return dict(params, sign=digest)


def api_items(payload):
    """官方 API 可能根据版本返回 data/list/rows，容错但不猜造价格。"""
    hits = []
    def visit(x):
        if isinstance(x, list):
            for obj in x:
                visit(obj)
        elif isinstance(x, dict):
            title = x.get("article_title") or x.get("post_title") or x.get("title")
            url = x.get("article_url") or x.get("post_url")
            if title and url:
                published = x.get("article_pubdate") or x.get("post_time") or x.get("pubdate")
                ts = None
                if published:
                    try:
                        ts = datetime.fromisoformat(str(published).replace(" ", "T")).replace(tzinfo=CHINA)
                    except ValueError:
                        pass
                subtitle = scrape_text(x.get("article_subtitle") or "")
                if any(w in (str(title) + " " + subtitle) for w in EXCLUSIONS):
                    return
                numeric = x.get("digital_price")
                try:
                    verified_price = float(numeric) if numeric not in (None, "") else extract_price(subtitle)
                except (ValueError, TypeError):
                    verified_price = None
                o = normalize(str(title), str(url), "值得买官方好价 API", ts,
                              price_override=verified_price)
                if o:
                    hits.append(o)
            else:
                for value in x.values():
                    if isinstance(value, (list, dict)):
                        visit(value)
    visit(payload)
    return hits


def fetch(url, accept="application/rss+xml"):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; wool-radar-free/1.0; public-offer-monitor)",
        "Accept": accept})
    with urllib.request.urlopen(req, timeout=18) as response:
        return response.read(2_000_000)


def read_offers(fixture=None):
    if fixture:
        obj = json.loads(Path(fixture).read_text(encoding="utf-8"))
        return [x for item in obj.get("offers", []) if
                (x := normalize(item["title"], item["url"], "测试样例"))], []

    offers, errors = {}, []
    key, secret = os.getenv("SMZDM_APP_KEY", ""), os.getenv("SMZDM_APP_SECRET", "")
    if key and secret:
        params = signed_params({"app_key": key,
                                "timestamp": int(datetime.now().timestamp()), "channel_ids": "1,2"}, secret)
        url = API + "?" + urllib.parse.urlencode(params)
        try:
            payload = json.loads(fetch(url, "application/json"))
            if payload.get("error_code") not in (0, "0", None):
                errors.append("官方 API 返回非成功状态，需检查账户授权及申请接口权限")
            else:
                for item in api_items(payload):
                    offers[item["id"]] = item
        except Exception as exc:
            errors.append("官方 API 无法读取：" + type(exc).__name__)
    else:
        errors.append("未配置官方 AppKey/Secret，暂使用公开 RSS")

    # 公共 RSS：只有成功拿到有效数据才认可；403 不绕过、不自动抓登录 Cookie。
    for source in RSS:
        try:
            payload = fetch(source)
            for item in rss_items(payload, source):
                offers[item["id"]] = item
        except Exception as exc:
            errors.append(source + " 无法读取：" + type(exc).__name__)
    # 免费备用源：公开线报是第三方转述，并非什么值得买直连。
    # 不可把公开标题价视为可复现的订单价；无发布日期时也不能声称当日实时价。
    for i, (source, path) in enumerate(PUBLIC_FEEDS):
        if i:
            time.sleep(6)
        try:
            items = scan.normalize(scan.fetch_json(path), source)
            accepted = 0
            for tip in items:
                item = normalize(tip["title"], tip["url"], source + "（间接线报，非值得买官方）")
                if item:
                    offers[item["id"]] = item
                    accepted += 1
            print(f"{source}: 找到 {accepted} 条标准化好价待核实线索")
        except Exception as exc:
            errors.append(source + " 读取失败：" + type(exc).__name__)
    return list(offers.values()), errors


def load_benchmarks(path=WATCHLIST):
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("benchmark 文件必须是 JSON 列表")
    return data


def match_benchmark(offer, benchmarks):
    title = offer["title"].lower()
    for item in benchmarks:
        terms = item.get("sku_terms", [])
        if not isinstance(terms, list) or not terms or not all(
            isinstance(term, str) and term.lower() in title for term in terms
        ):
            continue
        # 对比库存/状态一致的新商品，同 SKU 的匹配规则由人工维护。
        if item.get("condition") != "new_sealed":
            continue
        try:
            check_date = date.fromisoformat(item["checked_on"])
            if not date.today() - timedelta(days=7) <= check_date <= date.today() + timedelta(days=1):
                continue
            if not item.get("sale_evidence_url", "").startswith("https://"):
                continue
            expected = float(item["confirmed_sale_price"])
            if expected <= 0:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        return item
    return None


def profit(offer, benchmark):
    price = offer["purchase_price"]
    sale = float(benchmark["confirmed_sale_price"])
    fee = float(benchmark.get("platform_fee_rate", 0.016))  # 非保证，默认更保守鱼小铺
    inbound = float(benchmark.get("inbound_shipping", 0))
    outbound = float(benchmark.get("outbound_shipping", 10))
    risk = float(benchmark.get("risk_reserve", 10))
    if not (0 <= fee <= 0.1 and min(price, sale, inbound, outbound, risk) >= 0):
        raise ValueError("成本不合理")
    net = round(sale * (1 - fee) - price - inbound - outbound - risk, 2)
    margin = net / (price + inbound) if price + inbound > 0 else 0
    return {"net": net, "roi": margin, "sale": sale, "fee": fee,
            "qualified": net >= MIN_NET_PROFIT and margin >= MIN_NET_MARGIN}


def report(offers, benchmarks, errors):
    now = datetime.now(CHINA).strftime("%Y-%m-%d %H:%M")
    candidates = []
    validated = []
    for item in offers:
        benchmark = match_benchmark(item, benchmarks)
        if benchmark:
            result = profit(item, benchmark)
            if result["qualified"]:
                validated.append((item, benchmark, result))
        else:
            candidates.append(item)
    header = ["# 低价信息 → 闲鱼套利雷达（优先什么值得买）", "", f"最近检查（北京时间）：{now}", "",
              f"公开报价候选：{len(offers)}；具备人工成交价基准且达到试算阈值：{len(validated)}。", "",
              "> **注意**：下面只是选品线索，购买价和闲鱼成交价均可能变化；无真实成交依据不可称为套利机会。",
              "> 不自动下单、不自动在闲鱼发布、不绕过登录/风控。", "",
              "## 通过成本初筛的候选（仍须确认实际库存和成交价）", ""]
    for offer, bm, calc in validated[:20]:
        title = markdown_escape(offer["title"])
        header.append(
            f"- [{title}]({offer['url']}) · 买入标题价¥{offer['purchase_price']:.2f} "
            f"· 已录入闲鱼参考成交¥{calc['sale']:.2f} · **试算净利¥{calc['net']:.2f}** "
            f"· ROI {calc['roi']:.1%} · [成交价证据]({bm['sale_evidence_url']})")
    if not validated:
        header.append("暂时没有同时满足：同SKU近期成交价证据、净利润≥¥30、净ROI≥18%的项目。")
    header.extend(["", "## 待核实闲鱼价格的好价线索", ""])
    candidates.sort(key=candidate_priority)
    header += ["", "> 小件排序优先考虑¥25–¥300的手动工具/小型收纳配件。所需售价仅是达到净利/收益率阈值的数学门槛，不是闲鱼实际行情。", ""]
    for o in candidates[:35]:
        minimum = trial_minimum_sale_price(o["purchase_price"])
        header.append(f"- [{markdown_escape(o['title'])}]({o['url']}) · {o['category']} · {markdown_escape(o['source'])} · 标题价约¥{o['purchase_price']:.2f} · 若按手续费1.6%、运费8元、售后预留10元计算，**须卖到至少¥{minimum:.2f}才符合试单阈值**；仍须核实正常零售价、结算价和闲鱼真实成交证据。")
    if not candidates:
        header.append("没有可用且符合初筛的近期报价。")
    if errors:
        header.extend(["", "## 数据源状态", *["- " + markdown_escape(e) for e in errors]])
    header.extend(["", "> 间接线报数据不等于什么值得买官方报价；没有官方 API 密钥时不能称为完整扫描什么值得买。", ""])
    import xianyu_market
    header.extend([""] + xianyu_market.markdown_section())
    header += ["", "## 核价要求", "",
               "- 报价是否真能复现（会员券、地区补贴、限购、运费、订单限额）；商品必须为相同品牌、型号、规格、全新/二手状态。",
               "- 闲鱼要看**已成交**依据；挂价不是成交价。手填数据在 data/resale-benchmarks.json，默认空白。",
               "- 成本=实际到手价+进货运费+出货运费+平台费+退货售后准备金；试算值不能保证成交。",
               "- 只建议已入手验货后的如实上架；不发布无库存或虚假现货。", ""]
    return "\n".join(header), len(validated)


def main(fixture=None, dry_run=False):
    offers, errors = read_offers(fixture)
    benchmarks = load_benchmarks()
    doc, count = report(offers, benchmarks, errors)
    print(f"报价初筛={len(offers)}，核价通过={count}，数据源告警={len(errors)}")
    if dry_run:
        print(doc)
        return 0
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(doc, encoding="utf-8")
    return 0  # 抓不到数据时报告明确告警，不假装查到了套利。
    

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--fixture")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    sys.exit(main(a.fixture, a.dry_run))

#!/usr/bin/env python3
"""免费奶茶咖啡线报雷达：公开 API + 新闻 RSS + 已核对的活动时间表。
不登录品牌账号、不模拟抢券、不执行下单或领奖。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import scan

CHINA = ZoneInfo("Asia/Shanghai")
TODAY = lambda: datetime.now(CHINA).date()
SOURCES = {
    "线报酷最新": "/plus/json/push.json",
    "线报酷赚客吧": "/plus/json/push_16.json",
    "线报酷新赚吧": "/plus/json/push_18.json",
    "线报酷微博": "/plus/json/push_10.json",
    "线报酷猜你喜欢": "/plus/json/rank/guesslike.json",  # 官方公开 JSON，至少300秒间隔
}
SEARCHES = ("奶茶 免单 免费喝 when:7d", "咖啡 免费 0元 免单 when:7d")
STATE = Path("data/drinks-seen.json")
REPORT = Path("reports/drinks-latest.md")
CAMPAIGNS = Path("data/drink-campaigns.json")
DRINK_WORDS = ("奶茶", "咖啡", "饮品", "茶饮", "酸奶", "拿铁", "生椰", "蜜雪", "瑞幸", "库迪",
               "霸王茶姬", "古茗", "茶百道", "沪上阿姨", "茉酸奶", "爷爷不泡茶", "喜茶", "奈雪", "益禾堂", "书亦")
DEAL_WORDS = ("免单", "免费喝", "免费领", "0元", "零元", "0.01元", "一分钱",
              "1分钱", "1元喝", "一元喝", "抢券", "抽免单", "秒杀免费", "免费一杯",
              "免费咖啡", "免费奶茶", "免单券", "0.1元")
DISQUALIFY = ("充值", "开户", "信用卡", "贷款", "拉人", "邀请好友", "刷单", "返佣",
              "先消费", "先付款", "买一送一", "满减", "满赠", "第二杯", "砍价", "拼团",
              "专属邀请码", "新人福利", "邀请码", "推广码", "复制链接", "预存", "押金")
EXPIRED_RANGE = re.compile(r"(?:至|到|—|–|~|～|-)\s*(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日")
MAX_SEEN = 3500


def safe_href(url):
    if not isinstance(url, str) or len(url) > 1800:
        return None
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    if parsed.hostname not in ("new.ixbk.net", "new.xianbao.fun", "news.google.com",
                               "i.ifeng.com", "feng.ifeng.com", "www.ctdsb.net"):
        return None
    return url


def normalize_news(payload, source, now=None):
    if isinstance(payload, str):
        payload = payload.encode()
    root = ET.fromstring(payload)
    now = now or datetime.now(CHINA)
    items = []
    for node in root.findall(".//item")[:80]:
        title = scan.clean(node.findtext("title"))[:180]
        link = safe_href((node.findtext("link") or "").strip())
        descr = scan.clean(node.findtext("description"))[:240]
        if not title or not link:
            continue
        pub = (node.findtext("pubDate") or "").strip()
        try:
            timestamp = parsedate_to_datetime(pub)
            if timestamp.tzinfo is None:
                continue
            published = timestamp.astimezone(CHINA).date()
            if published > now.date() + timedelta(days=1) or published < now.date() - timedelta(days=10):
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        items.append({"id": hashlib.sha256(link.encode()).hexdigest()[:20],
                      "title": title, "url": link, "content": descr,
                      "source": source, "published": published.isoformat()})
    return items


def expired_by_text(text, today):
    """识别显式'至10月4日'一类结束日期；没检测出来绝不等于活动仍有效。"""
    endings = []
    for match in EXPIRED_RANGE.finditer(text):
        year = int(match.group(1) or today.year)
        try:
            endings.append(date(year, int(match.group(2)), int(match.group(3))))
        except ValueError:
            continue
    return bool(endings) and max(endings) < today


def classify(item, today=None):
    today = today or TODAY()
    title = item["title"]
    content = item.get("content", "")
    body = title + " " + content
    if not any(s in body for s in DRINK_WORDS) or not any(s in body for s in DEAL_WORDS):
        return None
    if any(s in body for s in DISQUALIFY):
        return None
    if expired_by_text(body, today):
        return None
    # 明确保留'待官方核实'，绝不将报道标题视为能领到手。
    high_priority = any(s in body for s in ("0.01元", "一分钱", "免单券", "免费喝", "0元", "零元"))
    item = dict(item)
    item["label"] = "疑似免费/一分钱" if high_priority else "待核实限量抢券"
    return item


def load_campaigns(today):
    if not CAMPAIGNS.exists():
        return []
    payload = json.loads(CAMPAIGNS.read_text(encoding="utf8"))
    active = []
    for camp in payload:
        if date.fromisoformat(camp["start"]) <= today <= date.fromisoformat(camp["end"]):
            link = safe_href(camp["source"])
            if link:
                active.append({**camp, "source": link})
    return active


def feed_url(query):
    return "https://news.google.com/rss/search?q=" + quote(query) + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"


def fetch_news(query):
    url = feed_url(query)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; beverage-deals-news-reader/1.0)",
                                   "Accept": "application/rss+xml,application/xml,text/xml"})
    with urlopen(request, timeout=22) as resp:
        return resp.read(1_800_000)


def get_records(fixture=None):
    records, errors = {}, []
    if fixture:
        sample = json.loads(Path(fixture).read_text(encoding="utf8"))
        for name, data in sample["linebao"].items():
            for item in scan.normalize(data, name):
                records[item["id"]] = item
        for name, xml in sample.get("news", {}).items():
            for item in normalize_news(xml, name):
                records[item["id"]] = item
        return records, errors

    for i, (source, path) in enumerate(SOURCES.items()):
        if i:
            time.sleep(6)  # 尊重线报酷 V2 接口至少5秒访问间隔
        try:
            for item in scan.normalize(scan.fetch_json(path), source):
                records[item["id"]] = item
        except (HTTPError, URLError, TimeoutError, ValueError, ET.ParseError) as exc:
            errors.append(source + ": " + type(exc).__name__)
    for query in SEARCHES:
        try:
            payload = fetch_news(query)
            for item in normalize_news(payload, "Google News RSS"):
                records[item["id"]] = item
        except (HTTPError, URLError, TimeoutError, ValueError, ET.ParseError) as exc:
            errors.append("新闻 RSS: " + type(exc).__name__)
    return records, errors


def md(text):
    return scan.markdown_escape(str(text)).replace("\n", " ")


def make_report(campaigns, leads, total, errors, first_run):
    now = datetime.now(CHINA).strftime("%Y-%m-%d %H:%M")
    lines = ["# 免费奶茶咖啡雷达", "",
             f"北京时间 {now}，本次读取 {total} 条公开线索，发现 {len(leads)} 条新增候选。", "",
             "> **重要：所有活动均须以品牌官方活动页面为准；本程序不验证库存、中奖或具体门店资格。**",
             "> 仅自动搜集信息，不使用账号、不替你抢券、不自动下单。", "",
             "## 已核对报道日期的活动（不是保证仍有奖券）", ""]
    if campaigns:
        for entry in campaigns:
            lines.extend([f"- **{md(entry['brand'])}**｜{md(entry['benefit'])}｜有效期报道：{entry['start']}～{entry['end']}",
                          f"  - 参与方式：{md(entry['how'])}；条件：{md(entry['conditions'])}。",
                          f"  - [原始报道]({entry['source']})（未核实剩余库存）"])
    else:
        lines.append("没有仍在已知活动期内的手工核对项目。")
    lines.extend(["", "## 自动发现的公开线索（都未核实能否领取）", ""])
    if first_run:
        lines.extend(["首次运行：仅建立基线和生成报告，不为既有活动推送提醒。", ""])
    for lead in leads[:35]:
        lines.append(f"- **{md(lead['label'])}** [{md(lead['title'])}]({lead['url']}) · {md(lead['source'])}" +
                     (f" · 文章日期：{lead['published']}" if lead.get("published") else ""))
    if not leads:
        lines.append("暂无符合过滤条件的新线索。")
    if errors:
        lines.extend(["", "## 数据源告警", *["- " + md(s) for s in errors]])
    lines.extend(["", "---", "数据源：线报酷许可的 JSON 列表接口与公开 Google News RSS；不访问线报详情页、不自动抢券。", ""])
    return "\n".join(lines)


def github_issue(message):
    token, repository = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY")
    if not token or not repository:
        print("未配置 GitHub Issue 权限，跳过提醒")
        return
    from urllib.request import Request, urlopen
    def request(method, url, payload=None):
        data = json.dumps(payload, ensure_ascii=False).encode() if payload else None
        headers = {"Accept": "application/vnd.github+json", "Authorization": "Bearer " + token,
                   "User-Agent": "wool-radar-free/drinks", "X-GitHub-Api-Version": "2022-11-28"}
        if data:
            headers["Content-Type"] = "application/json"
        with urlopen(Request(url, data=data, headers=headers, method=method), timeout=25) as resp:
            return json.load(resp)
    base = f"https://api.github.com/repos/{repository}/issues"
    title = "奶茶咖啡免费抢 · " + TODAY().isoformat()
    existing = request("GET", base + "?state=open&per_page=100")
    issue = next((x for x in existing if x.get("title") == title and "pull_request" not in x), None)
    if issue:
        request("POST", issue["comments_url"], {"body": message[:55000]})
    else:
        issue = request("POST", base, {"title": title, "body": message[:55000]})
    print("新线报提醒：", issue["html_url"])


def run(fixture=None, dry_run=False):
    today = TODAY()
    campaigns = load_campaigns(today)
    records, errors = get_records(fixture)
    if not records and not campaigns:
        print("所有源不可用且没有已知有效期内的活动", file=sys.stderr)
        return 2
    try:
        old = json.loads(STATE.read_text(encoding="utf8")) if STATE.exists() else []
    except (ValueError, OSError):
        old = []
    if not isinstance(old, list):
        old = []
    seen = set(old)
    first_run = not STATE.exists()
    all_leads = [x for x in (classify(i, today) for i in records.values()) if x]
    new_leads = [x for x in all_leads if x["id"] not in seen]
    report = make_report(campaigns, all_leads if first_run else new_leads,
                         len(records), errors, first_run)
    print(f"记录 {len(records)} 条；疑似奶茶咖啡免单 {len(all_leads)} 条；新增 {len(new_leads)} 条；人工核对活动 {len(campaigns)} 项")
    if dry_run:
        print(report)
        return 0
    STATE.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf8")
    STATE.write_text(json.dumps(list(dict.fromkeys(old + [i["id"] for i in all_leads]))[-MAX_SEEN:],
                                ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    if new_leads and not first_run:
        github_issue(make_report([], new_leads, len(records), errors, False))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.exit(run(args.fixture, args.dry_run))

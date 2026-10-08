#!/usr/bin/env python3
"""只读扫描线报酷官方 JSON 列表 API，发现新增的零本金羊毛候选。"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE = "https://new.ixbk.net"
SOURCES = {
    "最新": "/plus/json/push.json",
    "赚客吧": "/plus/json/push_16.json",
    "新赚吧": "/plus/json/push_18.json",
    "值得买": "/plus/json/push_19.json",
}
KEYWORDS = ("红包", "现金", "立减金", "签到", "提现", "金币", "极速版",
            "免费领", "免单", "话费", "支付宝", "微信支付", "返现", "免费拿")
EXCLUDE = ("邀请", "拉新", "拉人", "助力", "好友", "开户", "信用卡",
           "贷款", "借款", "投资", "充值", "预存", "保证金", "付费",
           "刷单", "垫付", "买会员", "购买", "下单", "消费", "满减",
           "多开", "接码", "实名", "首充", "首单", "拼团")
AMOUNT = re.compile(r"(?<!\d)(\d{1,4}(?:\.\d{1,2})?)\s*(?:元|块)(?!\d)")
SEEN_PATH = Path("data/seen.json")
REPORT_PATH = Path("reports/latest.md")
MAX_SEEN = 4000


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", str(value or "")))).strip()


def objects(value):
    if isinstance(value, list):
        for element in value:
            yield from objects(element)
    elif isinstance(value, dict):
        if "title" in value and "url" in value:
            yield value
        else:
            for element in value.values():
                if isinstance(element, (dict, list)):
                    yield from objects(element)


def safe_url(raw):
    if not isinstance(raw, str):
        return None
    url = urljoin(BASE + "/", raw.strip())
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http") or parsed.hostname not in ("new.ixbk.net", "new.xianbao.fun"):
        return None
    if parsed.username or parsed.password:
        return None
    return url


def normalize(payload, source):
    found = []
    for record in objects(payload):
        title, url = clean(record.get("title")), safe_url(record.get("url"))
        if not title or not url:
            continue
        found.append({
            "id": hashlib.sha256(url.encode()).hexdigest()[:20],
            "url": url,
            "title": title[:180],
            "content": clean(record.get("content"))[:400],
            "source": source,
        })
    return found


def amount(item):
    """标题宣传金额；不是实际到账金额。"""
    numbers = [float(s) for s in AMOUNT.findall(item["title"])]
    return min(numbers) if numbers else None


def candidate(item):
    title = item["title"]
    combined = title + " " + item["content"][:140]
    if not any(word in combined for word in KEYWORDS):
        return False
    if any(word in combined for word in EXCLUDE):
        return False
    value = amount(item)
    return value is not None and value >= 1


def markdown_escape(s):
    return re.sub(r"[\\\[\]`*|]", "", s)[:180]


def fetch_json(path):
    req = Request(
        BASE + path,
        headers={"User-Agent": "wool-radar-free/1.1 (public-list-api)", "Accept": "application/json"}
    )
    with urlopen(req, timeout=20) as response:
        data = response.read(3_000_000)
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return json.loads(data.decode(encoding))
        except (UnicodeError, json.JSONDecodeError):
            continue
    raise ValueError("API 未返回有效 JSON")


def build_report(entries, errors, first_run):
    now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M 北京时间")
    lines = ["# 赛博捡垃圾雷达", "",
             f"扫描于 {now} · 本轮新增候选：{len(entries)}", "",
             "> 仅为公开社区线报，**不保证可以领取或提现**。金额取自标题，不代表实际到账。", ""]
    if first_run:
        lines.extend(["首次扫描建立去重基线，不发送旧线报提醒。", ""])
    for item in entries[:35]:
        name = markdown_escape(item["title"])
        lines.append(f"- [{name}]({item['url']}) · {markdown_escape(item['source'])} · 标称 {amount(item):g} 元")
    if not entries:
        lines.append("暂无满足条件的新增线报。")
    if errors:
        lines.extend(["", "## 接口告警", *["- " + markdown_escape(e) for e in errors]])
    lines.extend(["", "---", "仅使用官方开放的 JSON 列表 API；请求间隔至少6秒，不访问详情页、不做自动领奖。", ""])
    return "\n".join(lines)


def create_issue(report):
    token, repository = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY")
    if not token or not repository:
        print("未设置 GitHub Token/Repository，仅保存报告。")
        return
    url = f"https://api.github.com/repos/{repository}/issues"
    title = "赛博捡垃圾 · " + datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")

    def request(method, url, payload=None):
        data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
        headers = {"Accept": "application/vnd.github+json",
                   "Authorization": "Bearer " + token,
                   "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "wool-radar-free"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = Request(url, data=data, method=method, headers=headers)
        with urlopen(req, timeout=25) as response:
            return json.load(response)

    issues = request("GET", url + "?state=open&per_page=100")
    issue = next((x for x in issues if x.get("title") == title and "pull_request" not in x), None)
    if issue is None:
        issue = request("POST", url, {"title": title, "body": "自动汇总公开线报，需自行核实活动。"})
    request("POST", issue["comments_url"], {"body": report[:60000]})
    print("提醒已添加：", issue["html_url"])


def scan(fixture=None, dry_run=False):
    old = []
    first_run = not SEEN_PATH.exists()
    if not first_run:
        try:
            old = json.loads(SEEN_PATH.read_text(encoding="utf8"))
            if not isinstance(old, list):
                old = []
        except (OSError, ValueError):
            old = []
    seen = set(x for x in old if isinstance(x, str))
    records, errors = {}, []
    samples = json.loads(Path(fixture).read_text(encoding="utf8")) if fixture else None
    for idx, (name, path) in enumerate(SOURCES.items()):
        if idx and samples is None:
            time.sleep(6)
        try:
            payload = samples[name] if samples is not None else fetch_json(path)
            items = normalize(payload, name)
            print(f"{name}: 读取 {len(items)} 条")
            for item in items:
                records[item["id"]] = item
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as exc:
            errors.append(f"{name}: {type(exc).__name__} {str(exc)[:90]}")
    if not records:
        print("扫描失败，全部数据源不可用：" + "; ".join(errors), file=sys.stderr)
        return 2
    matches = [x for x in records.values() if x["id"] not in seen and candidate(x)]
    print(f"去重后 {len(records)} 条，符合新增条件 {len(matches)} 条；首次运行={first_run}")
    report = build_report(matches if not first_run else [], errors, first_run)
    if dry_run:
        print(report)
        return 0
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf8")
    SEEN_PATH.write_text(json.dumps(list(dict.fromkeys(old + list(records)))[-MAX_SEEN:], ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    if matches and not first_run:
        create_issue(report)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture")
    parser.add_argument("--dry-run", action="store_true")
    options = parser.parse_args()
    sys.exit(scan(options.fixture, options.dry_run))

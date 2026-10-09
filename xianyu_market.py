#!/usr/bin/env python3
"""Offline Xianyu ASKING-price evidence module.

Only accepts manually supplied/otherwise authorized data. Never visits Xianyu,
does not reuse login cookies, and NEVER calls asking prices realized sales.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

INPUT = Path("data/xianyu-listings.json")
ALLOWED_HOSTS = {"www.goofish.com", "goofish.com", "h5.m.goofish.com",
                 "m.goofish.com", "www.2.taobao.com"}
MIN_SAMPLES = 5
MAX_AGE_DAYS = 7


def safe_listing_url(url):
    if not isinstance(url, str) or len(url) > 1800:
        return False
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    return (p.scheme == "https" and p.hostname in ALLOWED_HOSTS
            and not p.username and not p.password)


def parse_record(x, today=None):
    """Invalid, old, and wrong-condition records must never affect reference prices."""
    today = today or date.today()
    if not isinstance(x, dict):
        return None
    sku = x.get("sku")
    url = x.get("listing_url")
    condition = x.get("condition")
    status = x.get("status")
    price = x.get("asking_price")
    when = x.get("observed_on")
    if not isinstance(sku, str) or not 3 <= len(sku.strip()) <= 100:
        return None
    if condition != "new_sealed" or status != "listed" or not safe_listing_url(url):
        return None
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        return None
    if not math.isfinite(price) or not 10 <= price <= 5000:
        return None
    try:
        d = date.fromisoformat(when)
    except (ValueError, TypeError):
        return None
    if not today - timedelta(days=MAX_AGE_DAYS) <= d <= today:
        return None
    return {"sku": sku.strip(), "asking_price": round(float(price), 2),
            "listing_url": url, "observed_on": d.isoformat()}


def summarize(listings, today=None):
    """Summarize active ASKING listings only; no seller/order data is collected."""
    if not isinstance(listings, list):
        raise ValueError("xianyu-listings.json must contain a JSON array")
    if len(listings) > 5000:
        raise ValueError("Too many manually supplied observations")
    groups = defaultdict(dict)
    rejected = 0
    for row in listings:
        sample = parse_record(row, today)
        if sample is None:
            rejected += 1
            continue
        # one URL counted once: avoids faking market depth by repeated snapshots
        groups[sample["sku"]][sample["listing_url"]] = sample

    output = {}
    for sku, distinct in groups.items():
        values = sorted(o["asking_price"] for o in distinct.values())
        item = {"sku": sku, "sample_count": len(values), "sufficient": len(values) >= MIN_SAMPLES}
        if item["sufficient"]:
            q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
            iqr = q3 - q1
            cleaned = [x for x in values if q1 - 1.5 * iqr <= x <= q3 + 1.5 * iqr]
            if len(cleaned) < MIN_SAMPLES:
                item["sufficient"] = False
            else:
                p25 = statistics.quantiles(cleaned, n=4, method="inclusive")[0]
                item.update({"lower_quartile_asking": round(p25, 2),
                             "median_asking": round(statistics.median(cleaned), 2),
                             "sample_count_after_iqr": len(cleaned)})
        output[sku] = item
    return output, rejected


def markdown_section(path=INPUT, today=None):
    title = ["## 闲鱼挂牌价参考（人工导入，**不是成交价**）", ""]
    if not path.exists():
        return title + ["尚未提供价格样本；不可计算真实闲鱼售价。", ""]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        markets, rejected = summarize(data, today)
    except (ValueError, OSError, TypeError) as e:
        return title + [f"挂牌价样本读取失败：{type(e).__name__}；本轮不据此评估套利。", ""]

    if not markets:
        title += ["目前没有有效的、最近7天内的全新未拆封商品挂牌价样本。", ""]
    else:
        title += ["| 严格SKU | 独立有效挂牌样本 | 低四分位挂牌价 | 挂牌中位数 | 证据等级 |",
                  "|---|---:|---:|---:|---|"]
        for sku, row in sorted(markets.items()):
            name = sku.replace("|", r"\|").replace("\n", " ")[:100]
            if row["sufficient"]:
                title.append(f"| {name} | {row['sample_count_after_iqr']} "
                             f"| ¥{row['lower_quartile_asking']:.2f} "
                             f"| ¥{row['median_asking']:.2f} | 仅挂牌参考 |")
            else:
                title.append(f"| {name} | {row['sample_count']} | — | — | 样本不足（需≥5） |")
        title.append("")
    title += [f"无效/超期/状态不符的样本：{rejected}条。",
              "价格样本只代表挂牌意愿，不代表买家实际成交；不能以此生成“已验证利润”提醒。",
              "不读取登录态、手机号、卖家资料或订单，也不自动访问闲鱼网站。", ""]
    return title


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default=str(INPUT))
    args = p.parse_args()
    print("\n".join(markdown_section(Path(args.input))))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""只读核实现金奖励平台的官方规则。不会登录、签到、模拟浏览或请求提现。"""
from __future__ import annotations

import argparse
import html
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

# 只通过平台发布的规则页作事实证据；页面未明确授权第三方自动化时绝不标记可自动领取。
PLATFORMS = [
    ("红果短剧", "https://lf9-cdn-tos.draftstatic.com/obj/ies-hotsoon-draft/fqnovel/drama-rule.html"),
    ("番茄免费小说", "https://lf3-cdn-tos.draftstatic.com/obj/ies-hotsoon-draft/fqnovel/novel-activity-rule.html"),
    ("抖音极速版（金币优惠规则）", "https://lf9-cdn-tos.draftstatic.com/obj/ies-hotsoon-draft/douyin/5a1cc135-724a-4e76-b100-b198813a1697.html"),
]
REPORT = Path("reports/cash-eligibility.md")


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fragments = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.skipping += 1

    def handle_endtag(self, tag):
        if tag in ("style", "script") and self.skipping > 0:
            self.skipping -= 1

    def handle_data(self, data):
        if not self.skipping:
            self.fragments.append(data)

    def text(self):
        return html.unescape(" ".join(self.fragments))


def assess(text, platform_name):
    """仅能核对官方规则声明，不验证个人实际领取/提现。"""
    mentions_cash = bool(re.search(r"金币.{0,60}?(?:兑换成现金|兑换为现金|现金收益)|现金收益", text))
    mentions_withdrawal = "提现" in text and bool(re.search(r"支付宝|微信|支付账户", text))
    mentions_anti_automation = bool(re.search(r"模拟器|非官方客户端|外挂|插件|软件工具", text))
    # 强制采用三道证据门槛：官方现金规则 + 第三方自动化明确允许 + 真实提现到账。
    return {
        "official_cash_claim": mentions_cash and mentions_withdrawal,
        "platform_anti_cheat_clause": mentions_anti_automation,
        "automation_authorized": False,  # 该规则页从未明示授权第三方自动签到
        "verified_withdrawal": False,     # 无授权账号、无支付流水，无法独立验证
        "fully_verified": False,
        "platform": platform_name,
    }


def retrieve(url):
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; wool-radar-free rules-audit/1.0)",
        "Accept": "text/html",
    })
    with urlopen(request, timeout=20) as response:
        content = response.read(700_000)
    extractor = TextExtractor()
    extractor.feed(content.decode("utf-8", errors="replace"))
    return extractor.text()


def report():
    now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 可提现现金与自动化资格核查",
        "",
        f"最后检查：北京时间 {now}",
        "",
        "**提示：本文不会自动签到，不会领取现金，也没有证明任何脚本可以实际提现。**",
        "",
        "| 平台 | 官方规则明确支持兑换/提现 | 规则涉及自动化风险 | 第三方无人值守领取获授权 | 真实到账已核验 |",
        "|---|---|---|---|---|",
    ]
    for name, url in PLATFORMS:
        try:
            info = assess(retrieve(url), name)
            cash = "是" if info["official_cash_claim"] else "未证实（规则可能变化）"
            restrictions = "涉及" if info["platform_anti_cheat_clause"] else "需进一步人工复核"
            lines.append(f"| [{name}]({url}) | {cash} | {restrictions} | 未核实授权 | 未核实 |")
            print(f"{name}: 规则读取成功, 现金规则={cash}, 风险条款={restrictions}")
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            print(f"{name}: 读取失败 {type(exc).__name__}: {exc}")
            lines.append(f"| [{name}]({url}) | 读取失败，未知 | 未知 | 未核实授权 | 未核实 |")
    lines += [
        "",
        "## 社区开源脚本候选（不等于官方授权）",
        "",
        "- [1nbeat/kuaishou-check-in](https://github.com/1nbeat/kuaishou-check-in)：README 描述通过账号 Cookie 请求快手签到接口；需抓取敏感登录信息，**不接入**。未看到第三方自动化授权或可核对的提现回执。",
        "- [smallfawn/QLScriptPublic](https://github.com/smallfawn/QLScriptPublic)：多种签到脚本，主要为会员积分、优惠券等，不能直接算作人民币到账。",
        "",
        "## 下一步的严格通过条件",
        "",
        "1. 官方规则明确允许通过第三方接口自动签到或自动领取，不需要模拟观看广告或绕过风控。",
        "2. 使用免费公共 GitHub Actions 能按计划获得奖励，且无需在公开日志、Issue 或仓库内容中暴露账号密钥。",
        "3. 奖励明确可提人民币；有实际账户成功入账并完成提现的证据。",
        "",
        "在全部满足之前，不能宣传成'挂机赚钱'，不使用账号 Cookie 或部署自动领奖脚本。",
        ""
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-network", action="store_true", help="运行内置离线自检，仅测试规则解析")
    args = parser.parse_args()
    if args.no_network:
        demo = "金币每日自动兑换成现金，支付宝提现；禁止使用模拟器、非官方客户端和外挂"
        data = assess(demo, "离线样例")
        assert data["official_cash_claim"] and data["platform_anti_cheat_clause"]
        assert not data["fully_verified"] and not data["verified_withdrawal"]
        print("离线解析测试通过；未执行真实签到或提现")
    else:
        report()

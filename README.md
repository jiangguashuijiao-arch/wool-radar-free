# 赛博捡垃圾雷达 wool-radar-free

免费 GitHub Actions 定时扫描公开中文羊毛线报，按关键词过滤、去重，输出最新报告和 GitHub Issue 提醒。

只检索公开信息；不收集账号密码或 Cookie，不自动播放短视频、刷广告、点击广告或领取奖励。

数据源：线报酷 [开放接口说明 V2](https://new.ixbk.net/gonggao/1138711.html)。只查询官方允许的 JSON 列表接口，每次访问间隔至少 6 秒。

## 使用

在 GitHub **Actions** 中选择“赛博捡垃圾扫描”，点击 **Run workflow** 手动测试。首次成功运行会建立去重基线，不发送旧活动提醒。随后计划在北京时间每天 09:23、12:23、15:23、18:23、21:23 运行。GitHub 定时任务可能延迟。

新候选会汇总到 **Issues**；扫描结果在 `reports/latest.md`，历史去重在 `data/seen.json`。打开 GitHub 仓库的 Watch 可以订阅相关动态。

如提示 `Resource not accessible by integration` 或不能推送状态文件，请在 **Settings → Actions → General → Workflow permissions** 检查工作流读写权限（仓库/组织策略可能限制）。

## 风险

线报金额不代表实际到账，标题宣传、活动适用资格和提现门槛要人工验证。项目不会模拟用户观看视频，也不会绕过验证码或任何平台限制。GitHub Actions 初始免费且有配额/使用条款，以 GitHub 当期规则为准。

## 离线检查

```bash
python -m unittest discover -s tests -v
python scan.py --fixture tests/sample.json --dry-run
```

## 奶茶咖啡 0元/0.01元福利雷达

独立工作流：[奶茶咖啡免费抢券雷达](.github/workflows/drinks.yml)。计划北京时间每天 07:17、09:17、10:37、11:17、13:17、16:17、20:17 运行，GitHub 的定时执行可能延迟；不保证恰好赶上整点开抢。

- 自动检索 [线报酷公开 JSON API](https://new.ixbk.net/gonggao/1138711.html) 与 Google News 公共 RSS，尝试发现“免单券、免费一杯、0元、0.01元、限量抢券”等活动。
- reports/drinks-latest.md 为扫描报告，data/drinks-seen.json 用于去重。报道活动期的少量活动配置在 data/drink-campaigns.json；**仅说明报道日期，没有核实剩余名额**。
- 只有新线报才创建独立的“奶茶咖啡免费抢”GitHub Issue（首次运行建基线，不批量推送旧消息）。某些活动会要求会员、粉丝群、抽奖或特定门店。
- 过滤已知过期日期、明显充值、先付款、买一赠一和疑似拉新推广内容；无法可靠识别所有活动限制或最新库存。标题含免费也**绝不表示你已经中奖或可随时领取**。
- 本项目只监控公开资讯，不模拟抢券、不调用用户账号接口、不绕过验证码、不自动下单。实付价格和奖券能否使用都应以品牌 APP/小程序里的活动页为准。

手动执行：GitHub Actions → 奶茶咖啡免费抢券雷达 → Run workflow。
本地离线检查：python -m unittest discover -s tests -v。


## 什么值得买 → 闲鱼实物转卖套利雷达

独立模块：arbitrage.py；工作流：.github/workflows/arbitrage.yml；报告：reports/arbitrage-latest.md。
计划北京时间每日 08:46、12:46、16:46、20:46 检查（GitHub 定时触发可能延迟）。

**重要：不是自动买卖。** 系统只收集什么值得买好价、初步识别商品品类和文字里的参考实付价，再与由你人工录入的闲鱼「近期同款同成色实际成交价」比对。
发布闲鱼商品必须在你拿到货并验货后由你自己发布，不会自动创建虚假现货或抓取买卖双方隐私数据。

### 官方数据源（推荐）

什么值得买 [开发者开放 API](https://openapi.zhidemai.com/pages/) 需申请 AppKey、AppSecret 与好价接口授权，可能有免费的测试配额，具体以开发者平台审批为准。
获得授权后，在本仓库的 **Settings → Secrets and variables → Actions → New repository secret** 里创建：
- SMZDM_APP_KEY
- SMZDM_APP_SECRET

不要将任何密钥放入仓库文件、Issue 或评论。没申请成功前程序会尝试官方公开 RSS（feed.smzdm.com 与 fx.smzdm.com/feed）；公开 RSS 也可能返回 HTTP 403 或过期，报告会如实写出数据源错误而不会冒充成功找到报价。不要用抢券模拟器、网站 Cookie 或旁路反爬代替正规授权。

### 闲鱼成交价证据（手工）

新建或编辑 data/resale-benchmarks.json。默认是空列表（表示**没有经验证的闲鱼成交价**），不能由程序凭空生成利润。录入示意（**纯虚构样例，不是真实行情**）：

~~~json
[
  {
    "sku_terms": ["SN580", "1TB"],
    "condition": "new_sealed",
    "checked_on": "2026-10-09",
    "confirmed_sale_price": 390,
    "sale_evidence_url": "https://www.goofish.com/",
    "platform_fee_rate": 0.016,
    "inbound_shipping": 0,
    "outbound_shipping": 10,
    "risk_reserve": 15
  }
]
~~~

请替换成**自己核实的实际成交订单依据**，而不是普通挂价或卖家口述。要确保同品牌、同型号、同容量、同销售包装、同保修状态，不要拿不同容量价格对比。录入时更新 checked_on 日期及真实依据链接。若无法提供真实成交依据，则保持空列表。
报告仅在试算净利≥30元且净收益率≥18%时列入可复核候选；这是筛选阈值，不是利润承诺。
闲鱼交易手续费按个人/鱼小铺及订单不同可能改变；默认用较保守的1.6%试算，并需核实账号实际费率与退货成本。

### 禁止误把低价当套利

排除：国补/省补、以旧换新、捆绑购买、二手拆机、定金预售、只对首单/指定会员开放的价；
手机、虚拟权益、口令券、存储卡和不明来源商品未列入首批扫描。
不确保发布即成交。不能在没有实物时描述为“全新现货”或“个人闲置”。

离线检查：

~~~bash
python -m unittest discover -s tests -v
python arbitrage.py --fixture tests/fixtures-arbitrage.json --dry-run
~~~

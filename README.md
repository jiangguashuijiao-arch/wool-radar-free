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

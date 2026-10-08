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

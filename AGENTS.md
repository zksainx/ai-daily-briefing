# 仓库维护约定

本仓库运行「采集候选 → 短名单 → 核验 Top 10 → Markdown → 邮件」工作流，默认用简体中文交流。当前运行方式、时间窗口和文件路径以 [README.md](README.md) 为准；编辑规则见 [日报 skill](skills/daily-briefing/SKILL.md)。

- 保持 `python -m ai_daily_briefing --dry-run --no-save` 可用。采集层输出不能冒充已完成的 Top 10。
- 不提交日报、收件人名单、SMTP 密码、X Token 或本机运行状态。
- 业务代码放在 `ai_daily_briefing/`，`scripts/` 只保留启动入口。LaunchAgent 依赖的脚本路径必须可用。
- 仓库报告默认保留最近 30 个自然日，代码位于 `ai_daily_briefing/retention.py`；不得扩大到仓库外状态、日志和发送账本。
- 修改文档时同步检查引用，避免重新加入已移除的个人画像、Web3、强制 HTML 或社交平台发稿流程。
- 手动测试默认不发送邮件；发送必须有用户授权。现有定时任务按既定收件人名单执行。

## 修改代码后的验收

```bash
.venv/bin/python -m compileall -q ai_daily_briefing scripts
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m ai_daily_briefing --dry-run --no-save
```

修改抓取逻辑时另做一次真实联网验证。外部源失败应保留成功采集结果，并记录失败原因。

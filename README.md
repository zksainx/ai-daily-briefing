# AI 前沿日报

[中文](README.md) | [English](README_EN.md)

面向国内外 AI 工业界的中文邮件日报，覆盖模型、多模态、世界模型、具身智能、Agent、产品、基础设施和商业进展；不收录纯学术或 Web3 内容。

## 项目架构

```text
ai-daily-briefing/
├── ai_daily_briefing/        # Python 业务包
│   ├── __main__.py          # 采集命令入口：python -m ai_daily_briefing
│   ├── collector.py         # 多源采集、规范化、时间过滤、去重、候选包
│   ├── workflow.py          # 两阶段编辑、核验、断点恢复、发布与发送
│   ├── delivery.py          # 邮件预览和发送命令
│   ├── email.py             # 邮件正文渲染、SMTP、收件人与发送账本
│   ├── store.py             # SQLite 历史与来源健康记录
│   ├── retention.py         # 仓库内日期报告的 30 天保留规则
│   └── html.py              # 按需生成独立 HTML，定时邮件流程不使用
├── scripts/                 # 启动脚本与 skill 安装器
├── skills/daily-briefing/    # 编辑规则、候选采集助手、Markdown 校验
├── tests/                   # 单元测试与命令入口测试
├── email/                   # SMTP 配置模板、收件人模板及本机名单
├── outputs/                 # 最终 Markdown 报告，不进入 Git
├── config.yaml              # 来源、采集限流、80→30→10、保留天数
├── requirements.txt
├── EMAIL_SETUP.md           # SMTP 与邮件使用说明
└── .github/workflows/       # CI 验证
```

数据流：来源 → 原始候选包（最多 80 条）→ Codex 短名单（最多 30 条）→ 核验与 Top 10 → Markdown → 邮件正文 → 逐人发送并记账。

业务代码统一在包内，`scripts/scheduled_briefing.py` 和 `scripts/send_briefing_email.py` 是薄启动入口。现有 LaunchAgent 继续调用前者，无需因目录整理而更换路径。

## 安装与验证

需要 Python 3.11+。完整编辑流程还需要已安装、已登录且可用的 Codex CLI；邮件发送需要 SMTP 配置。

在仓库根目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# 离线样例，不联网、不保存、不发送
.venv/bin/python -m ai_daily_briefing --dry-run --no-save

# 编译与测试
.venv/bin/python -m compileall -q ai_daily_briefing scripts
.venv/bin/python -m unittest discover -s tests
```

旧的 `python briefing.py` 已替换为 `python -m ai_daily_briefing`。采集器输出是原始候选，不是最终精编日报。

## 使用方式

### 采集与生成

```bash
# 仅联网采集，输出 JSON 候选包到终端，不保存、不发送
.venv/bin/python -m ai_daily_briefing --editorial-packet --no-save

# 查看运行状态，不生成、不发送、不清理
.venv/bin/python -m ai_daily_briefing.workflow --check

# 生成或恢复当天任务；完成后向当前收件人名单发送
.venv/bin/python -m ai_daily_briefing.workflow

# 生成或恢复当天任务，不发送邮件
.venv/bin/python -m ai_daily_briefing.workflow --no-send

# 只清理过期报告
.venv/bin/python -m ai_daily_briefing.workflow --cleanup-only
```

只有明确要处理历史日期时才传 `--report-date YYYY-MM-DD`。已完成的任务会跳过；这些命令不强制重新生成或重发。

来源与数量配置在 [config.yaml](config.yaml)。Codex 可执行文件默认从 PATH 查找，可通过 `BRIEFING_CODEX` 指定路径。编辑模型固定为 `gpt-6.1-sol`，思考深度为 `high`。

### 邮件预览

将日期替换为已有报告的日期：

```bash
.venv/bin/python -m ai_daily_briefing.delivery \
  --markdown outputs/briefing_YYYY-MM-DD.md \
  --preview /tmp/briefing-email.html
```

预览不会发送。配置 SMTP、修改名单和手动发送见 [EMAIL_SETUP.md](EMAIL_SETUP.md)。实际名单为 `email/recipients.txt`，每行一个地址，发送前去重。邮件逐人发送，其他收件地址不公开。

也可执行 `./scripts/install-codex-skill.sh` 安装本地 skill，再调用 `$daily-briefing`。助手只使用本地项目，不会自动克隆旧上游；单独安装 skill 时可设置 `DAILY_BRIEFING_PROJECT` 指向本仓库。

## 每日规则与定时任务

- 北京时间每天 08:00 启动；消息窗口为前一日 08:00（含）至当日 08:00（不含），报告日期取窗口结束日。
- 最多 80 条原始候选 → 最多 30 条短名单 → 核验后最多 10 条。采集不按关键词打分筛选，各内容类别没有固定名额。
- 上期已发送事件默认排除；有新版本、新可用性、新基准或重大进展才允许再次收录。证据不足时少发，不凑数。
- 每条分别包含 2–3 句「概述」和 2–3 句「技术总结」，保留原始链接。邮件主题为 `AI前沿日报｜YYYY-MM-DD`。
- 最终只保存 `outputs/briefing_YYYY-MM-DD.md`。邮件 HTML 和纯文本正文在内存中生成。
- 阶段失败后保留进度，按 10、30、60 分钟设置重试等待，由每小时检查触发。自动恢复仅处理当天，跨日不补做。
- 日期、收件地址和可选修订编号组成发送记录，重试只向尚未成功的地址发送。

现有 macOS LaunchAgent 配置位于 `~/Library/LaunchAgents/com.kxzhang.ai-briefing-email-daily.plist`，每天 08:00 启动并每 3600 秒检查一次。该文件属于本机配置，新机器需另行安装定时任务。08:00 是启动时间，邮件在完成编辑后送达；睡眠或断网可能延迟运行。

```bash
launchctl print gui/$(id -u)/com.kxzhang.ai-briefing-email-daily
tail -n 80 ~/Library/Logs/ai-daily-briefing/email-daily.log
tail -n 80 ~/Library/Logs/ai-daily-briefing/email-daily-error.log
```

## 文件与保留期限

| 位置 | 用途与保留策略 |
| --- | --- |
| `outputs/` 及仓库根目录的日期报告 | 最近 30 个自然日，含今天；自动直接删除更早文件 |
| `~/Library/Application Support/ai-daily-briefing/runs/YYYY-MM-DD/` | 候选、短名单、核验进度、草稿与阶段状态，继续保留 |
| `~/Library/Logs/ai-daily-briefing/` | 日志与 `email-state.json` 发送账本，继续保留 |
| `email/recipients.txt` | 实际收件人，不进入 Git |
| `~/.config/ai-daily-briefing/email.env` | SMTP 配置；密码可存 macOS 钥匙串，不进入 Git |

保留天数由 `output.retention_days` 配置，默认 30。按报告文件名中的日期计算，不依赖修改时间。每次定时启动或采集器保存文件时清理；只匹配带合法日期的 `briefing_`、`candidates_`、`editorial_packet_`、`weekly_review_` 文件及 MD、HTML、TXT、JSON 扩展名，不递归、不跟随符号链接、不清理仓库外目录。

[日报 skill](skills/daily-briefing/SKILL.md) 保存编辑规则，[AGENTS.md](AGENTS.md) 保存维护约定。项目仓库：[zksainx/ai-daily-briefing](https://github.com/zksainx/ai-daily-briefing)。本地日报、候选包和周报均被 Git 忽略。

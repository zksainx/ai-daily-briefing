---
name: daily-briefing
description: 生成带跨日变化、可信度分层和技术总结的每日 AI 工业界简报。
tags: [daily, briefing, news, ai, industry, github]
---

# 每日早报 Skill

> Codex 的标准可安装版本位于 `skills/daily-briefing/`。本文件保留为 Claude Code、Hermes 和其他 Agent 的兼容入口。

## 触发条件

- 用户说「给我今日早报」「生成早报」「最新模型发布」「daily briefing」
- 定时任务需要生成每日 AI 工业界简报
- 需要把当天热点整理成中文自媒体选题

## 推荐执行方式

普通自动化或无模型环境，直接运行确定性 Markdown 版本：

```bash
python briefing.py --format markdown
```

在 Codex 里优先直接调用 `$daily-briefing`。Skill 内部默认使用两阶段精编：

```bash
skills/daily-briefing/scripts/run-daily-briefing.sh \
  --editorial-packet \
  --output-file outputs/editorial_packet.json
```

先由 Python 抓取、去重并永久保存最多 80 条候选，再由当前 Codex 模型先选 30 条短名单；第二阶段只核验短名单并完成最终 Top 10、中文解释和 X 草稿。阶段间保存短名单、核验进度和草稿，失败后从已有状态继续，不重复采集。不得补写候选包里不存在的事实或数字，所有条目保留原始可点击链接。每条必须分别包含 `概述：` 和 `技术总结：` 两个缩进段落，各写 2 至 3 句；前者说明主体、变化、可用范围和结果，后者说明来源支持的架构、接口、部署、实现、测试或产品机制。信息不足时减少入选条目，不重复或编造凑句数。

定时日报的候选池只取报告截止时间前 48 小时内且有明确发布日期的内容；Top 10 优先当天发布。前一天已经发送过的事件默认排除，只有新版本、新可用性、新基准或重大进展才允许重复；仅更换链接或标题不算新进展。

保存 Codex 精编版后运行概括质检：

```bash
python skills/daily-briefing/scripts/validate-briefing.py outputs/briefing_YYYY-MM-DD.md
```

如果只是验证环境是否能跑：

```bash
python briefing.py --dry-run --no-save
```

当前默认仅邮件交付：精编版通过质检后只保存 MD，由定时任务直接生成邮件正文并发送。仅在用户明确要求网页时生成同名交互 HTML：

```bash
python skills/daily-briefing/scripts/render-briefing-html.py outputs/briefing_YYYY-MM-DD.md
```

HTML 保留最终 Markdown 内容，并提供搜索、栏目导航、可信度与产业层筛选、本地收藏、主题切换、Markdown 下载和打印/PDF；单文件可直接打开，不依赖服务器或外部 CDN。

如果用户要纯文本：

```bash
python briefing.py --format text
```

## 输出结构

1. 相比昨天的新变化
2. AI 产业链全景与跨层联动
3. 最新模型发布与产品更新
4. 应用层趋势与 AI 投融资
5. 可能爆火的 AI 新闻
6. 模型公司官方账号动态
7. 今日必须看
8. 适合发 X 的选题与 B端/商业机会
9. 持续跟踪与 X 草稿
10. AI / 投资 / GitHub 明细

## 反馈闭环

当用户对本次早报说“看了”“收藏了”“准备写”“已经发了”“没价值”时，从当前早报或精编包找到对应条目的链接，直接记录反馈：

```bash
python briefing.py --feedback "<链接>" --feedback-action opened
python briefing.py --feedback "<链接>" --feedback-action saved
python briefing.py --feedback "<链接>" --feedback-action drafted
python briefing.py --feedback "<链接>" --feedback-action published
python briefing.py --feedback "<链接>" --feedback-action dismissed
```

能从上下文确定条目时不要再让用户重复提供标题。反馈只做有限加减分，不能覆盖时效和可信度。

用户说“生成本周简报复盘”“看看这周哪些内容最有用”时：

```bash
python briefing.py --weekly-review
```

周复盘包含持续信号、反馈偏好、来源成功率和下周动作。

默认保存 Markdown 并由定时任务发送邮件，新闻标题和项目名都带可点击链接。采集最多 80 条原始候选，由 Agent 阅读核验后选出最多 10 条；可信度标注为 `官方确认`、`多源印证` 或 `单源信号`。每条保留具体中文概括，不加“摘要”“一句话介绍”“中文总结”等前缀；质检器会拦截缺少概括、只有元数据或命中空泛模板的条目。独立网页 HTML 仅按明确请求生成。

## 重要规则

- 日期和星期必须由系统时间计算，不要靠猜。
- 外部网站抓取失败时，不要编造新闻；说明暂未抓到，并保留其他成功板块。
- `--dry-run` 是 Codex/CI 的稳定 smoke test，不能删。
- `--no-save`、`--dry-run`、`--no-history` 不写入跨日历史。
- 每次正常保存真实早报时，记录来源成功率、条数和耗时。
- 最终选稿由当前 Codex 根据产业重要性、时效、来源可信度、技术含量和来源多样性判断，不使用个人画像或旧版个性化分数。

## 数据源

- AI 热点：TechCrunch + OpenAI、Google DeepMind、Hugging Face 官方 RSS
- 模型发布：厂商官方 RSS/Sitemap/Changelog、19 个基础模型发布页，以及 42 个中美为主的官方 Hugging Face 组织页
- 官方账号：62 个中美模型公司和 AI 产品 X 官方账号；有 X API 时自动抓取，否则由 Codex 按清单联网检索
- AI 编程/Agent：Claude Code、Codex、Cursor、GitHub Copilot、Cognition/Devin、Replit 等官方 Changelog、Release 与 X 账号
- 多模态模型：Runway、Stability AI、Black Forest Labs、Midjourney、Luma、Pika、Kling、Vidu 等官方发布页与 X 账号
- 补充信号：Hacker News、Hugging Face Trending、AI HOT
- 产业信号：NVIDIA、AMD、MLCommons、AWS、Google Cloud、CoreWeave、Data Center Dynamics、Product Hunt、Crunchbase News 和 TechCrunch Venture
- 应用与资本：客户采用、用户增长、定价、收入、融资、并购、IPO 和财报；关键商业数字必须回到一手来源核验
- 官方追踪：Anthropic sitemap、指定 GitHub Releases
- 投资 & 经济：TechCrunch Venture 分类
- GitHub 项目：GitHub Trending

数据源和数量限制在 `config.yaml` 中维护。

生成时会过滤明显跑题的 AI 新闻，并按 URL 与标题相似度合并同一事件；媒体和官方来源交替混排，某个源失败不会影响其他板块。

模型发布必须以厂商官网、官方 Changelog、官方模型卡或官方 Release 为确认依据。媒体报道只能补充影响，不得替代第一手发布链接；本轮没有官方发布时要明确说明，不能用传闻或旧模型填充。

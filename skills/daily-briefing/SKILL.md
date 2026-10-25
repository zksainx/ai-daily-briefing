---
name: daily-briefing
description: Generate a source-linked Chinese AI industry daily briefing with a two-stage editorial pass, factual verification, and overview plus technical summaries, saved as Markdown for email delivery.
---

# Daily Briefing

## Scope and editorial rules

Cover domestic and international AI industry developments: model releases, multimodal and world models, embodied AI, agents, products, infrastructure, deployment, adoption, and major commercial events. Exclude pure academic research, cryptocurrency, and blockchain coverage.

Do not use a personal profile, named-person preference, keyword relevance score, or legacy personalization score. Read original titles and summaries. Judge industry significance, timeliness, source credibility, technical substance, and source diversity; categories have no fixed quotas.

Prefer original company announcements, model cards, changelogs, repositories, and official X posts. Media and community sources can discover leads; verify concrete claims against primary evidence where available. Do not invent dates, technical details, prices, benchmarks, funding, or availability. Distinguish official confirmation, corroboration, and single-source signals.

## Schedule and freshness

- Use Asia/Shanghai. The report date is the ending date of the exact window: previous day 08:00 inclusive to report day 08:00 exclusive.
- Reject outside-window and future-dated items. An unknown publication date is not eligible for the scheduled pool; sitemap modification time alone does not establish publication time.
- Read the previous sent report. Exclude repeated events unless there is a new version, new availability, a new benchmark, or a material new development. Rewording a title or changing a URL is insufficient.
- Automatic recovery handles only today's report after 08:00 and before midnight. Historical work requires an explicit user request; never automatically backfill missing dates.

## Run and resume

The scheduled entrypoint is `scripts/scheduled_briefing.py`, a stable wrapper for `ai_daily_briefing.workflow`. It fixes the editorial model to `gpt-6.1-sol` with `high` reasoning, persists artifacts, validates the draft, and sends from the final Markdown. The collector CLI is `python -m ai_daily_briefing`; business modules live in `ai_daily_briefing/`.

1. Collect up to 80 raw candidates into the daily packet. Collection is not a completed briefing.
2. Select up to 30 IDs for the shortlist; use 30 when enough candidates exist. Do not write long inclusion/exclusion reasons for all candidates.
3. Verify only the shortlist, then select up to 10 final items from it. External pages corroborate selected candidates, rather than silently replacing them with unrelated discoveries.
4. Save verification notes and draft progress so retries continue from existing artifacts. Do not recollect unless requested or the saved packet is unusable.
5. Validate the final Markdown before publication. Report the actual shortfall if fewer than 10 supported stories remain; never fill with stale or weak items.

Persistent artifacts live in `~/Library/Application Support/ai-daily-briefing/runs/YYYY-MM-DD/`. Do not put recoverable candidates or drafts in temporary directories. The full workflow and operations commands are documented in the project's README.

For manual candidate collection, the bundled helper accepts the collector CLI flags:

```bash
skills/daily-briefing/scripts/run-daily-briefing.sh --editorial-packet --no-save
```

When using an installed skill, invoke helpers by their absolute paths. Read every entry in `sections.editorial_queue`; do not treat Python's deterministic highlights as the final editorial selection.

For an open-ended discovery run, check the packet's official model/product watchlists and relevant industry search groups, including China. When `metadata.official_x_monitor.mode` is `codex_web_search`, execute the supplied official X search groups and respect the configured time window and candidate cap. Direct posts must originate from the configured official account. A watchlist entry is not proof that it was searched. For a fixed-pool run, stay within the supplied pool and use these pages only for verification.

A verified major model release within the window should be included unless it is a genuine duplicate. Preserve the exact model identity and distinguish foundation models from coding products or tools. Prefer original X posts to reposts, screenshots, or engagement statistics.

## Final Markdown and email

Save only `outputs/briefing_YYYY-MM-DD.md`. Use this structure for each item:

```markdown
1. [新闻标题](https://example.com/announcement)

   概述：2–3 句，说明谁发布了什么、变化、可用范围和结果。

   技术总结：2–3 句，写来源支持的架构、接口、部署、实现或测试细节。商业或政策新闻写产品机制、实施流程或基础设施细节，不编造技术。

   来源：来源名称 · 官方确认
```

Keep the Top 10 as news summaries. Do not add selection reasons, rebuttal-style endings, generic editorial judgments, social-media drafts, or project promotion. Confidence and uncertainty belong in source metadata.

Run the bundled validator and fix errors before returning a completed file:

```bash
python skills/daily-briefing/scripts/validate-briefing.py outputs/briefing_YYYY-MM-DD.md
```

Email is rendered from Markdown with inline title numbers and subject `AI前沿日报｜YYYY-MM-DD`. Do not create a standalone HTML reader unless explicitly requested. Send only when authorized; the scheduled runner uses the existing recipient list and per-recipient delivery ledger to avoid duplicates.

Repository report files are automatically retained for the most recent 30 calendar days, including today, as configured by `output.retention_days`. This does not delete external run state or the email ledger.

---
name: daily-briefing
description: Generate a source-linked Chinese AI industry daily briefing: collect up to 80 verified candidates, then let Codex editorially select up to 10 final items spanning models, products, infrastructure, adoption, and commercial events. Exclude academic-paper, cryptocurrency, and blockchain coverage; save the result as Markdown for email delivery; generate a standalone HTML reader only when explicitly requested.
---

# Daily Briefing

Use this skill directly in Codex. Do not require Hermes, Telegram, or a separate chat bot.

## Daily Selection Contract

The Python program is a collection and verification layer, not the final editor. On every daily run:

Completion requires the entire workflow: persist up to 80 candidates, select a 30-item shortlist, verify that shortlist, select up to 10, write the final Chinese Markdown, validate it, and prepare email delivery from that Markdown. The scheduled workflow may resume these stages across retries, but an interactive run should continue in the same turn whenever possible. Generate a standalone HTML companion only when explicitly requested. A collection success or candidate-file link is an intermediate result, never completion. If the current run already has a candidate packet, shortlist, verification progress, or draft, continue from those artifacts instead of starting over. Only stop after collection when the user explicitly requests collection only.

With `editorial.raw_candidates: true`, do not apply topical keyword exclusions or rule scores to the candidate pool. Read the original title and summary, then make editorial inclusion decisions. Stage 1 records only the 30 selected candidate IDs; do not spend context on long per-candidate inclusion/exclusion reasons. Stage 2 verifies only that shortlist and keeps concise resumable verification notes. When the user specifies choosing from an existing fixed candidate pool, keep final selections inside that pool; use external pages to verify those candidates. Broad X/watchlist discovery below applies to open-ended discovery runs, not this fixed-pool workflow. Preserve publication dates, reject future-dated entries, and check page publication dates rather than trusting sitemap modification times.

1. Collect and deduplicate up to 80 industry candidates into a permanent daily candidate packet.
2. Read each candidate's `raw_summary`, source, date, evidence level, and original URL, then select exactly 30 for the verification shortlist when at least 30 are available.
3. Verify the shortlist and independently select **up to 10** final items. Do not reproduce `sections.highlights` or sort solely by its scores.
4. Prefer material releases, capability or availability changes, production deployment, adoption evidence, infrastructure economics, and major commercial events. Down-rank awards, marketing claims, routine minor releases, duplicate coverage, stale announcements, and generic case studies.
5. If fewer than 10 recent, well-supported events remain, publish fewer items and state the shortfall. Never fill the list with stale or low-signal content.
6. Do not use a personal profile, named-person preference, or legacy personalization score. Judge the fixed candidate pool on industry significance, timeliness, source credibility, technical substance, and source diversity; Codex is the final editor.

### Freshness and cross-day deduplication

- The scheduled candidate pool is restricted to the 48 hours ending at the report-date cutoff; items without a usable publication date are not eligible for the scheduled pool.
- Prefer events published on the report date itself.
- Read the previous sent Markdown report before selecting Top 10. Exclude previously sent events by default.
- A repeated event is allowed only when the source shows a new version, new availability, a new benchmark result, or a material new development. A new URL or rewritten headline alone is not new progress.
- Never include an event older than 48 hours in the scheduled report.

## Generate Today's Briefing

1. Run the bundled helper to fetch, normalize, and deduplicate the source pool:

```bash
skills/daily-briefing/scripts/run-daily-briefing.sh \
  --editorial-packet \
  --output-file "outputs/editorial_packet_$(date +%F).json"
```

Translate explicit user constraints into helper flags without asking them to learn CLI syntax:

- `最近 48 小时模型发布与更新` → `--mode models --hours 48`
- `最近 7 天 AI 视频产品更新` → `--mode products --focus "AI视频" --hours 168`
- `最近 24 小时应用层趋势` → `--mode applications --hours 24`
- `最近 7 天 AI 投融资` → `--mode funding --hours 168`
- `今日 AI 全产业链简报` → `--mode industry --hours 24`
- `过去 24 小时医疗 AI 新闻` → `--mode hotspots --focus "医疗" --hours 24`
- `今日完整早报` → keep the default `--mode all`; do not narrow the existing source pool.

Append the selected flags to the helper command before generating the editorial packet.

When invoked from an installed skill, use the absolute path to this skill's `scripts/run-daily-briefing.sh`.

2. Read `sections.editorial_queue` first, then cross-check its entries against `sections.model_releases`, `sections.product_updates`, `sections.application_trends`, `sections.ai_funding`, and `sections.industry_chain`. Use the Daily Selection Contract above to choose the final ten. `raw_summary` contains source material for factual rewriting; do not discard it when the deterministic Chinese hint is generic.

3. When `metadata.official_x_monitor.mode` is `codex_web_search`, execute every query in `sections.official_x_search_groups` for the requested window. The groups are country-aware and put China first. Retain direct `https://x.com/<handle>/status/<id>` links, and add only posts published by the configured account. Also check `sections.official_model_watchlist` and `sections.official_product_watchlist` for vendors and products that do not expose a stable feed.

4. Execute the relevant batches in `sections.industry_search_groups`, starting with China. Use `sections.industry_source_watchlist` to return to company newsrooms, customer announcements, investors, exchanges, or regulatory filings. Discovery-only media and community sources may surface a lead, but they cannot confirm funding amounts, adoption figures, revenue, valuation, or infrastructure spending on their own.

5. Before writing, complete a freshness audit: confirm that every relevant X and industry search group was checked or name the failed group, and separately record first-party findings as `model release`, `product/function update`, `application/adoption`, `funding/commercial event`, `ecosystem activity`, or `potential viral story`. An account or page appearing in a watchlist is not evidence that it was searched. Do not finalize a briefing with an empty China official-source result until the CN groups have been checked explicitly.

6. Do not require a model launch for inclusion. Track major product releases, new features, application adoption, customer cases, user growth, pricing, revenue, partnerships, infrastructure, open-source projects, financing, policy or safety events, and industry disputes when they have clear AI relevance and credible links. Do not include academic papers, conference research, pure benchmarks, cryptocurrency/blockchain news, or community heat as final items. Treat popularity as a distribution signal, not proof of truth.

7. Classify each item on two separate axes: `industry_layer` is only `upstream`, `midstream`, or `downstream`; `event_types` describes what happened, such as `model_release`, `product_update`, `adoption`, `funding`, `acquisition`, `earnings`, or `policy`. Capital is a cross-cutting event, never a fourth industry layer. A downstream application company remains downstream after raising money.

8. Save the final document as `outputs/briefing_YYYY-MM-DD.md` in the project directory. Then run the bundled validator and return a clickable local file link only after it passes:

```bash
python skills/daily-briefing/scripts/validate-briefing.py \
  "outputs/briefing_$(date +%F).md"
```

When invoked from an installed skill, use the absolute path to `validate-briefing.py`. If validation fails, rewrite the named entries and run it again; do not silently return a partial draft.

For the email-only workflow, stop after validating Markdown; the scheduled runner renders email HTML and plain text in memory and sends them. Do not generate a standalone HTML file. Only if the user explicitly requests a web reader, run:

```bash
python skills/daily-briefing/scripts/render-briefing-html.py \
  "outputs/briefing_$(date +%F).md"
```

The renderer preserves the final Codex-edited Markdown and creates `outputs/briefing_YYYY-MM-DD.html`. It is a standalone file with local search, section navigation, confidence and industry-layer filters, browser-local bookmarks, Markdown download, print/PDF support, theme switching, and copy buttons for code or X drafts. It must not require a web server or external CDN. Return clickable links to both Markdown and HTML. If the user explicitly asks for only one format, honor that request.

9. Keep every factual claim within the candidate packet or the first-party pages/posts checked above. Preserve original URLs and numbers. Do not invent missing dates, scores, funding amounts, customer counts, revenue, benchmark results, or source agreement.

10. Use clickable Markdown titles. Every retained item must have two distinct, indented paragraphs before metadata: `概述：` uses 2-3 sentences to identify who did what, availability and the main result; `技术总结：` uses 2-3 sentences for source-supported architecture, interface, deployment, implementation, benchmark, product mechanism or rollout details. Both paragraphs are required, including for commercial and policy events, but never invent technical detail the source does not provide. Each sentence should add a distinct fact. The final Top 10 contains news summaries only: do not add `入选理由`, `为什么重要`, editorial judgments, or rebuttal-style endings such as `这不代表……`, `不能据此认为……`, or `仍需……`. Keep source confidence and uncertainty in the metadata line. Do not use generic filler such as `值得关注`, `可作为行业观察`, or `核心看点是工具链还不成熟` as the explanation.

11. Use these sections in order when relevant:

```text
本日十条行业信号
相比昨天的新变化
最新模型发布与更新
产品、平台与 Agent 更新
AI 产业链全景
应用层趋势与商业化
AI 投融资与商业化
持续观察
来源明细
```

12. Distinguish source confidence as `官方确认`, `多源印证`, or `单源信号`. Funding and commercial figures marked `待官方复核` must not be written as confirmed. If a source fails, retain successful sections and name the failed source briefly.

13. Make X drafts structurally different: include at least a single post, a thread, and a visual or video script when the candidate pool supports them.

14. End every final Markdown briefing with a concise bilingual support section. Use the heading `支持这个项目 / Support the Project`, invite readers in natural Chinese and English to Star the project if the briefing was useful, and include the canonical repository link exactly once: `https://github.com/Rion-Wu-tech/ai-daily-briefing`. Keep this section brief and place it after source notes so it does not compete with the briefing.

15. Before saving, audit every clickable item in the final Markdown. Reject the draft if any item is followed only by a source, tag, score, confidence label, or link. Also reject repeated template explanations that could describe several unrelated stories. Rewrite those entries from `raw_summary` and the original source facts. The bundled validator enforces the minimum structural and anti-filler checks; editorial factuality still requires Codex review.

## Official Model Release And Update Radar

Treat model launches and material model updates as a separate first-party intelligence track, not as ordinary hot news.

1. Check `sections.model_releases` before general headlines on every run, including when the user only asks for an AI briefing. This section includes launches plus material version, capability, availability, pricing, deprecation, and open-weight updates.
2. Confirm a launch with a vendor website, official RSS/sitemap, official changelog, official model card, or official GitHub Release. Media coverage may explain impact but cannot replace the release source.
3. For each model release, preserve the original title, exact source URL, `published_at`, `release_kind`, and any concrete model ID supplied by the packet.
4. Explain what changed, who can use it, how it is available (API, product, or open weights), and the technical details explicitly disclosed by the source. Never infer pricing, benchmarks, context length, license, or availability; omit details the source does not provide.
5. Keep release announcements separate from Hugging Face Trending and social heat. A trending model is a popularity signal unless it comes from a configured first-party organization.
6. If no official model release appears in the requested time window, say so plainly instead of filling the section with rumors or older launches.

## Official X Account Radar

Treat official X posts as a fast first-party signal layer. They are not a substitute for product documentation when exact API details matter.

1. Cover both US and China account groups from `sections.official_x_watchlist`; do not silently search only English-language labs.
2. Prefer original posts over reposts, quote-post commentary, screenshots, aggregators, or employee accounts.
3. For a model launch announced on X, preserve the direct post URL and then look for the matching vendor page, model card, changelog, or repository. Link both when available.
4. Include launch previews, availability changes, pricing/API notices, open-weight releases, benchmark reports, safety notices, and major product integrations when they are material.
5. Keep X engagement as a heat signal only. Likes and reposts do not increase factual confidence.
6. If X blocks or rate-limits retrieval, name that limitation and continue with official websites and model cards.
7. Cover three groups separately: foundation-model companies, AI coding/agent products (Claude Code, Codex, Cursor, Copilot, Devin, Replit), and multimodal model products (Runway, Stability, FLUX, Midjourney, Luma, Pika, Kling, Vidu). Do not call every product a foundation-model vendor.

## Targeted Briefings

Preserve the full source pool and default complete briefing. Apply targeting only when the user asks for it.

- `--mode models`: model launches and model updates, including version upgrades, capability changes, API availability, pricing, deprecations, and open-weight changes.
- `--mode products`: AI products, features, APIs, workflows, integrations, and pricing changes.
- `--mode applications`: downstream products, customer adoption, user growth, pricing, revenue, and industry deployment.
- `--mode funding`: AI financing, acquisitions, IPOs, and earnings across all three industry layers, with primary-source verification status.
- `--mode industry`: the upstream/midstream/downstream view, cross-layer topic connections, application trends, and capital/commercial events.
- `--mode hotspots`: potentially viral AI stories from the requested period, while retaining confidence labels and original links.
- `--focus "AI视频"`: limit the editorial result to a named track or industry. Accept natural topics such as Agent, AI coding, image/video, healthcare, finance, education, robotics, chips, search, or open source.
- `--hours 48`: retain verifiable items from the requested time window. For date-only sources, state that the exact boundary is uncertain instead of inventing a timestamp.

These options can be combined. Example: `--mode products --focus "医疗" --hours 168`.

## Deterministic Fallback

If the Codex editorial pass cannot be completed, save only a clearly labeled pending candidate file and state the concrete blocker. Do not present the collection output as a completed briefing:

```bash
skills/daily-briefing/scripts/run-daily-briefing.sh \
  --format markdown \
  --output-file "outputs/candidates_$(date +%F).md"
```

## Validate The Workflow

For installation or regression checks, run:

```bash
skills/daily-briefing/scripts/run-daily-briefing.sh --dry-run --no-save
```

## Record Feedback

Resolve the item URL from the current Markdown or editorial packet, then run one action without asking the user to repeat the link:

```bash
skills/daily-briefing/scripts/run-daily-briefing.sh --feedback "<URL>" --feedback-action opened
skills/daily-briefing/scripts/run-daily-briefing.sh --feedback "<URL>" --feedback-action saved
skills/daily-briefing/scripts/run-daily-briefing.sh --feedback "<URL>" --feedback-action drafted
skills/daily-briefing/scripts/run-daily-briefing.sh --feedback "<URL>" --feedback-action published
skills/daily-briefing/scripts/run-daily-briefing.sh --feedback "<URL>" --feedback-action dismissed
```

## Generate A Weekly Review

```bash
skills/daily-briefing/scripts/run-daily-briefing.sh --weekly-review
```

The default file is `outputs/weekly_review_YYYY-MM-DD.md`.

import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from briefing import DailyBriefing, parse_args, save_output
from briefing_html import render_markdown_html
from briefing_store import BriefingStore


class DailyBriefingTests(unittest.TestCase):
    def generate_quietly(self, briefing):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            return briefing.generate_data()

    def test_dry_run_text_contains_core_sections(self):
        briefing = DailyBriefing(dry_run=True)
        data = self.generate_quietly(briefing)
        output = briefing.format_output(data, "text")

        self.assertIn("原始候选采集", output)
        self.assertIn("等待编辑逐条判断并选择 Top 10", output)
        self.assertIn("OpenAI 发布新的开发者工具", output)
        self.assertNotIn("CoinDesk", output)

    def test_industry_profile_uses_raw_candidate_packet(self):
        briefing = DailyBriefing(dry_run=True)
        data = self.generate_quietly(briefing)
        markdown = briefing.format_output(data, "markdown")

        self.assertEqual(data["metadata"]["title"], "AI 工业界前沿简报")
        self.assertIn("# 原始候选采集", markdown)
        self.assertEqual(
            data["metadata"]["editorial_review"]["selection_method"],
            "agent_editorial_judgment",
        )
        self.assertNotIn("web3_news", data["sections"])

    def test_industry_highlights_fill_top_ten_and_filter_non_capital_infra(self):
        briefing = DailyBriefing(dry_run=True)
        candidates = [
            {
                "title": f"Company {index} launches an AI platform update",
                "url": f"https://example.com/{index}",
                "source": f"Official source {index % 5}",
                "overall_score": 100 - index,
                "section": "ai",
            }
            for index in range(12)
        ]

        highlights = briefing.generate_highlights(candidates)
        self.assertEqual(len(highlights), 10)
        infra_post = {
            "title": "AI inference latency optimization for cloud serving",
            "summary": "A practical guide to reduce model serving latency.",
            "description": "",
            "event_types": ["funding"],
            "industry_track": "infrastructure",
        }
        self.assertFalse(briefing._looks_like_ai_funding(infra_post))

    def test_json_output_is_valid(self):
        briefing = DailyBriefing(dry_run=True)
        data = self.generate_quietly(briefing)
        output = briefing.format_output(data, "json")
        parsed = json.loads(output)

        self.assertEqual(parsed["metadata"]["title"], "AI 工业界前沿简报")
        self.assertTrue(parsed["metadata"]["dry_run"])
        self.assertIn("ai_news", parsed["sections"])
        self.assertIn("highlights", parsed["sections"])
        self.assertIn("must_read", parsed["sections"])
        self.assertIn("changes", parsed["sections"])
        self.assertIn("business_opportunities", parsed["sections"])
        self.assertIn("watchlist", parsed["sections"])
        self.assertIn("model_releases", parsed["sections"])
        self.assertIn("product_updates", parsed["sections"])
        self.assertIn("industry_chain", parsed["sections"])
        self.assertIn("cross_layer_connections", parsed["sections"])
        self.assertIn("application_trends", parsed["sections"])
        self.assertIn("ai_funding", parsed["sections"])
        self.assertIn("industry_search_groups", parsed["sections"])
        self.assertIn("industry_source_watchlist", parsed["sections"])
        self.assertIn("viral_ai_news", parsed["sections"])
        self.assertIn("official_social_updates", parsed["sections"])
        self.assertIn("official_x_watchlist", parsed["sections"])
        self.assertIn("official_x_search_groups", parsed["sections"])
        self.assertIn("official_model_watchlist", parsed["sections"])
        self.assertIn("official_product_watchlist", parsed["sections"])
        self.assertIn("editorial_queue", parsed["sections"])
        self.assertIn("x_topics", parsed["sections"])
        self.assertIn("x_drafts", parsed["sections"])
        self.assertIn("summary_cn", parsed["sections"]["ai_news"][0])
        self.assertIn("category", parsed["sections"]["ai_news"][0])
        self.assertIn("tags", parsed["sections"]["ai_news"][0])
        self.assertIn("content_value", parsed["sections"]["ai_news"][0])
        self.assertIn("overall_score", parsed["sections"]["ai_news"][0])
        self.assertIn("business_score", parsed["sections"]["ai_news"][0])
        self.assertIn("timeliness_score", parsed["sections"]["ai_news"][0])
        self.assertIn("credibility_score", parsed["sections"]["ai_news"][0])
        self.assertNotIn("personalization", briefing.config)
        self.assertEqual(parsed["metadata"]["editorial_mode"], "codex-ready")
        self.assertGreater(
            parsed["metadata"]["official_x_monitor"]["search_group_count"], 0
        )
        self.assertTrue(
            parsed["metadata"]["industry_monitor"]["capital_is_cross_cutting"]
        )
        upstream_events = {
            item["event_type"]
            for item in parsed["sections"]["industry_chain"]["upstream"]
        }
        self.assertIn("infrastructure", upstream_events)
        self.assertTrue(
            all(
                item.get("signal_type") != "model_release"
                for item in parsed["sections"]["ai_news"]
            )
        )

    def test_markdown_has_highlights_and_x_topics(self):
        briefing = DailyBriefing(dry_run=True)
        data = self.generate_quietly(briefing)
        markdown = briefing.format_output(data, "markdown")

        self.assertIn("# 原始候选采集", markdown)
        self.assertIn("等待编辑逐条判断并选择 Top 10", markdown)
        self.assertNotIn("## 本日十条行业信号", markdown)
        self.assertEqual(len(data["sections"]["highlights"]), 0)
        self.assertGreaterEqual(len(data["sections"]["model_releases"]), 1)
        self.assertGreaterEqual(len(data["sections"]["product_updates"]), 1)
        self.assertGreaterEqual(len(data["sections"]["viral_ai_news"]), 1)
        self.assertTrue(
            all(
                item["verification"] == "官方确认"
                for item in data["sections"]["model_releases"]
            )
        )

    def test_html_output_is_interactive_and_self_contained(self):
        briefing = DailyBriefing(dry_run=True)
        data = self.generate_quietly(briefing)
        html = briefing.format_output(data, "html")
        soup = BeautifulSoup(html, "html.parser")

        self.assertEqual(soup.html.get("lang"), "zh-CN")
        self.assertIsNotNone(soup.select_one("#briefing-search"))
        self.assertIsNotNone(soup.select_one("#confidence-filter"))
        self.assertIsNotNone(soup.select_one("#layer-filter"))
        self.assertIsNotNone(soup.select_one("#saved-filter"))
        self.assertIsNotNone(soup.select_one("#source-markdown"))
        self.assertGreaterEqual(len(soup.select(".briefing-section")), 1)
        self.assertIn("原始候选采集", html)
        self.assertNotIn("<script src=", html)
        self.assertNotIn("<link rel=\"stylesheet\"", html)

    def test_html_renderer_preserves_final_markdown_content(self):
        markdown = (
            "# 近 24 小时 AI 简报｜2026-08-26\n\n"
            "## 最新模型发布与更新\n\n"
            "1. [示例模型](https://example.com/model)\n\n"
            "   示例公司公开了新模型，并提供 API 调用。\n\n"
            "   **可信度：官方确认｜产业层：中游**\n"
        )
        html = render_markdown_html(markdown, source_filename="briefing.md")
        soup = BeautifulSoup(html, "html.parser")
        card = soup.select_one(".briefing-card")

        self.assertEqual(soup.title.string, "近 24 小时 AI 简报｜2026-08-26")
        self.assertEqual(card.get("data-confidence"), "official")
        self.assertEqual(card.get("data-layer"), "midstream")
        self.assertIn("示例公司公开了新模型", card.get_text(" ", strip=True))
        self.assertEqual(card.a.get("href"), "https://example.com/model")

    @unittest.skipUnless(shutil.which("node"), "需要 Node.js 检查浏览器脚本语法")
    def test_generated_html_javascript_parses(self):
        briefing = DailyBriefing(dry_run=True)
        data = self.generate_quietly(briefing)
        html = briefing.format_output(data, "html")
        soup = BeautifulSoup(html, "html.parser")
        browser_script = soup.find_all("script")[-1].string or ""

        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "briefing-ui.js"
            script_path.write_text(browser_script, encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(script_path)],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_industry_profile_disables_x_drafts(self):
        briefing = DailyBriefing(dry_run=True)
        briefing.config["editorial"]["raw_candidates"] = False
        briefing.config["limits"]["x_topics"] = 5
        briefing.config["limits"]["x_drafts"] = 3
        data = self.generate_quietly(briefing)
        markdown = briefing.format_output(data, "markdown")
        text = briefing.format_output(data, "text")
        drafts = data["sections"]["x_drafts"]

        self.assertEqual(drafts, [])
        self.assertNotIn("```text", markdown)
        self.assertNotIn("X 草稿", text)

    def test_x_drafts_keep_source_diversity(self):
        briefing = DailyBriefing(dry_run=True)
        briefing.config["editorial"]["raw_candidates"] = False
        briefing.config["limits"]["x_topics"] = 5
        briefing.config["limits"]["x_drafts"] = 3
        items = []
        for section, name, title, tags in [
            ("ai", "AI 热点", "AI video tool", ["视频/多模态"]),
            ("venture", "投资 & 经济", "AI startup funding", ["融资/IPO"]),
            ("github", "GitHub 优质项目", "sample/agent-tool", ["Agent"]),
            ("github", "GitHub 优质项目", "sample/agent-tool-2", ["Agent"]),
        ]:
            items.append(
                {
                    "section": section,
                    "section_name": name,
                    "display_title": title,
                    "url": f"https://example.com/{title}",
                    "category": "Agent / AI 编码" if "Agent" in tags else "AI 行业动态",
                    "tags": tags,
                    "summary_cn": "适合做内容。",
                    "score": 90,
                    "content_value": "优先跟进",
                }
            )

        drafts = briefing.generate_x_drafts(items)
        sources = {draft["source"] for draft in drafts}

        self.assertIn("AI video tool", sources)
        self.assertIn("AI startup funding", sources)
        self.assertIn("sample/agent-tool", sources)

    def test_enrichment_has_no_personalization_fields(self):
        briefing = DailyBriefing(dry_run=True)
        project = {
            "name": "sample/codex-agent-workflow",
            "description": "Codex agent workflow toolkit for B2B automation.",
            "language": "Python",
            "stars": "1,000",
            "today_stars": "100 stars today",
            "url": "https://github.com/sample/codex-agent-workflow",
        }

        briefing._enrich_project_item(project)

        self.assertIn(project["content_value"], {"优先跟进", "适合发 X", "值得关注", "可看"})
        self.assertLessEqual(project["overall_score"], 96)
        self.assertNotIn("personal_relevance", project)
        self.assertNotIn("rion_score", project)
        self.assertNotIn("rion_reason", project)

    def test_general_ranking_does_not_add_personalization(self):
        briefing = DailyBriefing(dry_run=True)
        hot_generic = {
            "name": "popular/rom-manager",
            "description": "A beautiful app manager and player.",
            "language": "Python",
            "stars": "90,000",
            "today_stars": "2,000 stars today",
            "url": "https://github.com/popular/rom-manager",
        }
        agent_tool = {
            "name": "sample/codex-agent-workflow",
            "description": "Codex agent workflow toolkit for B2B automation.",
            "language": "Python",
            "stars": "2,000",
            "today_stars": "100 stars today",
            "url": "https://github.com/sample/codex-agent-workflow",
        }
        for project in [hot_generic, agent_tool]:
            briefing._enrich_project_item(project)

        items = briefing.all_content_items([], [], [hot_generic, agent_tool])
        briefing.generate_x_topics(items)
        self.assertTrue(all("rion_score" not in item for item in items))

    def test_highlights_keep_source_diversity(self):
        briefing = DailyBriefing(dry_run=True)
        items = [
            {
                "section": "github",
                "section_name": "GitHub 优质项目",
                "display_title": f"repo-{index}",
                "url": f"https://example.com/repo-{index}",
                "category": "开源生态",
                "tags": ["开源生态"],
                "summary_cn": "GitHub 热门项目。",
                "score": 100 - index,
            }
            for index in range(4)
        ]
        items.extend(
            [
                {
                    "section": "ai",
                    "section_name": "AI 热点",
                    "display_title": "AI browser update",
                    "url": "https://example.com/ai",
                    "category": "产品发布/更新",
                    "tags": ["浏览器"],
                    "summary_cn": "AI 产品入口变化。",
                    "score": 60,
                },
                {
                    "section": "venture",
                    "section_name": "投资 & 经济",
                    "display_title": "AI startup funding",
                    "url": "https://example.com/venture",
                    "category": "融资并购",
                    "tags": ["融资/IPO"],
                    "summary_cn": "AI 商业化继续被资本关注。",
                    "score": 58,
                },
            ]
        )

        highlights = briefing.generate_highlights(items)
        sections = [item["section"] for item in highlights]

        self.assertGreaterEqual(sections.count("GitHub 优质项目"), 1)
        self.assertIn("AI 热点", sections)
        self.assertIn("投资 & 经济", sections)

    def test_project_tags_avoid_common_false_positives(self):
        briefing = DailyBriefing(dry_run=True)
        cases = [
            (
                {
                    "name": "Zackriya-Solutions/meetily",
                    "description": "Meetily is a privacy-first meeting assistant with local transcription.",
                    "language": "TypeScript",
                    "stars": "1,000",
                    "today_stars": "100 stars today",
                    "url": "https://github.com/Zackriya-Solutions/meetily",
                },
                "Meta",
            ),
            (
                {
                    "name": "JuliusBrussee/caveman",
                    "description": "why use many token when few token do trick",
                    "language": "Rust",
                    "stars": "1,000",
                    "today_stars": "100 stars today",
                    "url": "https://github.com/JuliusBrussee/caveman",
                },
                "监管",
            ),
            (
                {
                    "name": "harvard-edge/cs249r_book",
                    "description": "Open book for machine learning systems.",
                    "language": "Jupyter Notebook",
                    "stars": "1,000",
                    "today_stars": "100 stars today",
                    "url": "https://github.com/harvard-edge/cs249r_book",
                },
                "端侧/硬件",
            ),
        ]

        for project, bad_tag in cases:
            with self.subTest(project=project["name"]):
                briefing._enrich_project_item(project)
                self.assertNotIn(bad_tag, project["tags"])

    def test_x_topics_keep_ai_and_venture_sources(self):
        briefing = DailyBriefing(dry_run=True)
        briefing.config["editorial"]["raw_candidates"] = False
        briefing.config["limits"]["x_topics"] = 5
        items = [
            {
                "section": "github",
                "section_name": "GitHub 优质项目",
                "display_title": f"repo-{index}",
                "url": f"https://example.com/repo-{index}",
                "category": "Agent / AI 编码",
                "tags": ["Agent"],
                "summary_cn": "GitHub 热门项目。",
                "score": 100 - index,
            }
            for index in range(4)
        ]
        items.extend(
            [
                {
                    "section": "ai",
                    "section_name": "AI 热点",
                    "display_title": "Mistral model update",
                    "url": "https://example.com/ai",
                    "category": "公司与模型",
                    "tags": ["Mistral"],
                    "summary_cn": "模型公司竞争加速。",
                    "score": 60,
                },
                {
                    "section": "venture",
                    "section_name": "投资 & 经济",
                    "display_title": "AI startup funding",
                    "url": "https://example.com/venture",
                    "category": "融资并购",
                    "tags": ["融资/IPO"],
                    "summary_cn": "资本继续押注 AI 商业化。",
                    "score": 58,
                },
            ]
        )

        topics = briefing.generate_x_topics(items)
        sources = {topic["source"] for topic in topics}

        self.assertIn("Mistral model update", sources)
        self.assertIn("AI startup funding", sources)

    def test_mistral_summary_is_not_overridden_by_openai_competitor_phrase(self):
        briefing = DailyBriefing(dry_run=True)
        item = {
            "title": "What is Mistral AI? Everything to know about the OpenAI competitor",
            "summary": "",
        }

        briefing._enrich_news_item(item, "ai")

        self.assertIn("Mistral", item["summary_cn"])
        self.assertIn("Mistral", item["tags"])
        self.assertNotIn("rion_reason", item)

    def test_regulation_tag_avoids_plain_rules_false_positive(self):
        briefing = DailyBriefing(dry_run=True)
        item = {
            "title": "The new rules of early-stage fundraising",
            "summary": "",
            "source": "Sample",
            "url": "https://example.com/fundraising-rules",
        }

        briefing._enrich_news_item(item, "venture")

        self.assertNotIn("监管", item["tags"])

    def test_anthropic_product_news_not_forced_into_chip_summary(self):
        briefing = DailyBriefing(dry_run=True)
        item = {
            "title": "Anthropic's new Claude feature is quietly selling you on AI",
            "summary": "",
            "source": "Sample",
            "url": "https://example.com/claude-feature",
        }

        briefing._enrich_news_item(item, "ai")

        self.assertIn("Anthropic", item["summary_cn"])
        self.assertNotIn("芯片和算力基础设施", item["summary_cn"])

    def test_outputs_include_chinese_summaries_for_each_item(self):
        briefing = DailyBriefing(dry_run=True)
        data = self.generate_quietly(briefing)
        items = [
            item
            for section in ["ai_news", "venture_news", "github_projects"]
            for item in data["sections"][section]
        ]

        markdown = briefing.format_output(data, "markdown")
        text = briefing.format_output(data, "text")

        self.assertNotIn("中文总结：", markdown)
        self.assertNotIn("中文总结：", text)
        self.assertNotIn("摘要：", markdown)
        self.assertNotIn("摘要：", text)
        self.assertNotIn("一句话介绍：", markdown)
        self.assertNotIn("一句话介绍：", text)
        for item in data["sections"]["editorial_queue"]:
            self.assertIn(item["raw_summary"], markdown)
            self.assertIn(item["raw_summary"], text)

    def test_markdown_puts_specific_summary_immediately_after_news_title(self):
        briefing = DailyBriefing(dry_run=True)
        lines = []
        item = {
            "title": "示例公司发布企业 Agent",
            "url": "https://example.com/agent",
            "source": "示例公司",
            "time": "今日",
            "summary_cn": "示例公司上线企业 Agent，可自动处理客服工单，并向付费客户开放。",
        }

        briefing._append_markdown_news(lines, "AI 热点", [item])

        self.assertEqual(lines[2], "1. [示例公司发布企业 Agent](https://example.com/agent)")
        self.assertEqual(lines[3], f"   {item['summary_cn']}")

    def test_editorial_packet_requires_specific_summary_for_every_item(self):
        briefing = DailyBriefing(dry_run=True)
        data = self.generate_quietly(briefing)
        instructions = " ".join(data["metadata"]["editorial_instructions"])

        self.assertIn("每一条", instructions)
        self.assertIn("主体", instructions)
        self.assertIn("不得用", instructions)
        self.assertTrue(
            all("raw_summary" in item for item in data["sections"]["editorial_queue"])
        )

    def test_config_limits_are_applied(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(
                "limits:\n"
                "  ai_news: 1\n"
                "  venture_news: 1\n"
                "  github_projects: 1\n"
                "  topics: 2\n",
                encoding="utf-8",
            )

            briefing = DailyBriefing(config_path=str(config_path), dry_run=True)
            data = self.generate_quietly(briefing)

        self.assertEqual(len(data["sections"]["ai_news"]), 1)
        self.assertEqual(len(data["sections"]["github_projects"]), 1)
        self.assertEqual(len(data["sections"]["topics"]), 2)

    def test_rss_parser_supports_link_and_guid_fallback(self):
        briefing = DailyBriefing(dry_run=True)
        briefing.config["quality"]["max_feed_age_days"] = 0
        feed = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel>
          <item>
            <title>OpenAI ships a new agent workflow</title>
            <description><![CDATA[<p>A useful <strong>agent</strong> update.</p>]]></description>
            <link>https://example.com/openai-agent</link>
            <pubDate>Fri, 10 Jul 2026 07:00:00 GMT</pubDate>
          </item>
          <item>
            <title>Hugging Face publishes a model guide</title>
            <description>Model deployment guide.</description>
            <guid>https://example.com/hf-model-guide</guid>
          </item>
        </channel></rss>"""

        rows = briefing._parse_feed_articles(feed, "Official AI", 5)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["url"], "https://example.com/openai-agent")
        self.assertEqual(rows[0]["summary"], "A useful agent update.")
        self.assertEqual(rows[1]["url"], "https://example.com/hf-model-guide")

    def test_official_feed_marks_model_launch_without_marking_enterprise_report(self):
        briefing = DailyBriefing(dry_run=True)
        model = {
            "title": "Introducing GPT-6",
            "summary": "A new frontier model is now available.",
        }
        report = {
            "title": "How enterprises put AI to work",
            "summary": "A report about adoption and workflows.",
        }
        application = {
            "title": "Putting sign language AI into users' hands",
            "summary": "A research model is now available to selected users.",
        }
        program = {
            "title": "Claude for nonprofits",
            "summary": "Anthropic is launching a social impact program.",
        }
        versioned_model = {
            "title": "Gemini 3.1 Pro",
            "summary": "The latest model in the Gemini family.",
        }

        briefing._mark_official_model_release(model)
        briefing._mark_official_model_release(report)
        briefing._mark_official_model_release(application)
        briefing._mark_official_model_release(program)
        briefing._mark_official_model_release(versioned_model)

        self.assertEqual(model["signal_type"], "model_release")
        self.assertTrue(model["official"])
        self.assertEqual(versioned_model["signal_type"], "model_release")
        self.assertNotIn("signal_type", report)
        self.assertNotIn("signal_type", application)
        self.assertNotIn("signal_type", program)

    def test_official_huggingface_org_returns_first_party_model_release(self):
        briefing = DailyBriefing(dry_run=False, history_enabled=False)
        briefing.config["quality"]["model_release_max_age_days"] = 0
        briefing.config["sources"]["official_model_orgs"] = [
            {"name": "Qwen", "author": "Qwen"}
        ]
        briefing._get_json = lambda url, params=None: [
            {
                "id": "Qwen/Qwen-Test-32B",
                "pipeline_tag": "text-generation",
                "likes": 88,
                "createdAt": "2026-08-12T08:00:00Z",
            }
        ]

        rows = briefing.fetch_official_model_orgs(limit_per_org=1)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["signal_type"], "model_release")
        self.assertEqual(rows[0]["release_kind"], "开源权重/模型卡")
        self.assertTrue(rows[0]["official"])
        self.assertEqual(
            rows[0]["url"], "https://huggingface.co/Qwen/Qwen-Test-32B"
        )

    def test_official_watchlists_cover_major_us_and_china_labs(self):
        briefing = DailyBriefing(dry_run=True)

        model_orgs = {
            row["name"]
            for row in briefing.config["sources"]["official_model_orgs"]
        }
        x_accounts = {
            row["name"]: row["handle"]
            for row in briefing.official_x_watchlist()
        }

        self.assertGreaterEqual(len(model_orgs), 42)
        self.assertTrue(
            {"OpenAI", "Microsoft", "NVIDIA", "Qwen", "DeepSeek", "Kimi", "MiniMax"}
            <= model_orgs
        )
        self.assertEqual(x_accounts["OpenAI"], "OpenAI")
        self.assertEqual(x_accounts["Qwen"], "Alibaba_Qwen")
        self.assertEqual(x_accounts["xAI"], "SpaceXAI")
        self.assertEqual(x_accounts["Tencent Hunyuan"], "TencentHunyuan")
        self.assertEqual(x_accounts["Huawei Cloud / Pangu"], "HuaweiCloud1")
        self.assertEqual(x_accounts["Claude"], "ClaudeAI")
        self.assertEqual(x_accounts["Grok"], "grok")
        self.assertEqual(x_accounts["Cursor"], "cursor_ai")
        self.assertEqual(x_accounts["Black Forest Labs"], "bfl_ai")
        self.assertEqual(x_accounts["Cerebras"], "Cerebras")
        self.assertEqual(x_accounts["Ant Ling"], "AntLingAGI")
        self.assertEqual(x_accounts["Wan"], "Alibaba_Wan")
        self.assertGreaterEqual(len(x_accounts), 61)
        product_pages = {
            row["name"] for row in briefing.official_product_page_watchlist()
        }
        self.assertTrue(
            {"Claude Code Changelog", "Cursor Changelog", "Grok Release Notes"}
            <= product_pages
        )

        feed_names = {
            row["name"] for row in briefing.config["sources"]["industry_feeds"]
        }
        self.assertTrue(
            {"NVIDIA Newsroom", "AMD Press Releases", "MLCommons", "SemiAnalysis"}
            <= feed_names
        )
        model_pages = {
            row["name"] for row in briefing.official_model_page_watchlist()
        }
        self.assertTrue(
            {
                "OpenAI API Changelog",
                "Claude Platform Release Notes",
                "Meta AI Blog",
                "Alibaba Model Studio Release Notes",
                "Volcano Ark Announcements",
                "Tencent Hunyuan Product Updates",
                "Baidu Qianfan Updates",
            }
            <= model_pages
        )
        self.assertNotIn("personalization", briefing.config)
        self.assertNotIn("web3_news", briefing.config["sources"])

    def test_official_source_config_has_no_duplicates_or_known_unofficial_accounts(self):
        briefing = DailyBriefing(dry_run=True)
        sources = briefing.config["sources"]

        for key, field in (
            ("official_model_orgs", "author"),
            ("official_model_pages", "url"),
            ("official_product_pages", "url"),
            ("official_x_accounts", "handle"),
        ):
            values = [str(row[field]).lower() for row in sources[key]]
            self.assertEqual(len(values), len(set(values)), key)

        handles = {
            row["handle"].lower() for row in sources["official_x_accounts"]
        }
        self.assertNotIn("claude_code", handles)
        self.assertNotIn("bfl_ml", handles)
        self.assertNotIn("inclusionai", handles)

    def test_official_x_api_updates_keep_direct_post_links(self):
        briefing = DailyBriefing(dry_run=False, history_enabled=False)
        briefing.config["sources"]["official_x_accounts"] = [
            {"name": "OpenAI", "handle": "OpenAI", "country": "US"}
        ]

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "data": [
                        {
                            "id": "123",
                            "author_id": "1",
                            "created_at": "2026-08-13T01:00:00Z",
                            "text": "Codex now supports a faster review workflow.",
                            "public_metrics": {
                                "like_count": 100,
                                "retweet_count": 10,
                            },
                        }
                    ],
                    "includes": {
                        "users": [
                            {"id": "1", "name": "OpenAI", "username": "OpenAI"}
                        ]
                    },
                }

        request_params = []

        def fake_get(*args, **kwargs):
            request_params.append(kwargs["params"])
            return Response()

        briefing.session.get = fake_get
        with patch.dict(os.environ, {"X_BEARER_TOKEN": "test-token"}):
            rows = briefing.fetch_official_x_updates()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["signal_type"], "official_social")
        self.assertEqual(rows[0]["url"], "https://x.com/OpenAI/status/123")
        self.assertTrue(rows[0]["official"])
        self.assertEqual(request_params[0]["max_results"], 10)
        self.assertIn("-is:retweet -is:reply", request_params[0]["query"])
        start_time = datetime.fromisoformat(
            request_params[0]["start_time"].replace("Z", "+00:00")
        )
        age = datetime.now(timezone.utc) - start_time
        self.assertGreater(age, timedelta(hours=23, minutes=59))
        self.assertLess(age, timedelta(hours=24, minutes=1))

    @patch("briefing.subprocess.run")
    def test_official_x_token_loads_from_macos_keychain(self, run):
        briefing = DailyBriefing(dry_run=True)
        run.return_value.stdout = "keychain-token\n"

        with patch("briefing.sys.platform", "darwin"), patch.dict(
            os.environ,
            {
                "X_BEARER_TOKEN": "",
                "X_BEARER_KEYCHAIN_SERVICE": "test-x-service",
                "X_BEARER_KEYCHAIN_ACCOUNT": "test-x-account",
            },
        ):
            token = briefing._x_bearer_token()

        self.assertEqual(token, "keychain-token")
        run.assert_called_once_with(
            [
                "security",
                "find-generic-password",
                "-w",
                "-a",
                "test-x-account",
                "-s",
                "test-x-service",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )

    def test_official_x_window_is_independent_from_report_window(self):
        briefing = DailyBriefing(dry_run=True, lookback_hours=48)

        payload = self.generate_quietly(briefing)

        self.assertEqual(payload["metadata"]["request"]["lookback_hours"], 48)
        self.assertEqual(
            payload["metadata"]["official_x_monitor"]["lookback_hours"], 24
        )
        self.assertEqual(
            payload["metadata"]["official_x_monitor"]["max_results_per_request"],
            10,
        )

    def test_official_x_uses_exact_report_cutoff_window(self):
        cutoff = datetime(2026, 9, 20, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        briefing = DailyBriefing(
            dry_run=False,
            history_enabled=False,
            report_cutoff=cutoff,
        )
        briefing.config["sources"]["official_x_accounts"] = [
            {"name": "OpenAI", "handle": "OpenAI", "country": "US"}
        ]
        request_params = []

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [], "includes": {"users": []}}

        def fake_get(*args, **kwargs):
            request_params.append(kwargs["params"])
            return Response()

        briefing.session.get = fake_get
        with patch.dict(os.environ, {"X_BEARER_TOKEN": "test-token"}):
            briefing.fetch_official_x_updates()

        self.assertEqual(request_params[0]["start_time"], "2026-09-18T16:00:00Z")
        self.assertEqual(request_params[0]["end_time"], "2026-09-19T16:00:00Z")
        self.assertEqual(briefing.x_usage_stats["api_calls"], 1)
        self.assertEqual(briefing.x_usage_stats["post_resources"], 0)

    def test_qwen_changelog_parser_keeps_qwen_and_excludes_third_party_models(self):
        briefing = DailyBriefing(dry_run=True)
        briefing.config["quality"]["model_release_max_age_days"] = 0
        soup = BeautifulSoup(
            """
            <main>
              <div>August 12, 2026</div>
              <h3 id="qwen-test">qwen-test-32b</h3>
              <p>A new Qwen model with tool use.</p>
              <h3 id="glm-test">ZHIPU/GLM-Test</h3>
              <p>A third-party model is available.</p>
            </main>
            """,
            "html.parser",
        )
        config = {
            "name": "QwenCloud",
            "url": "https://docs.qwencloud.com/changelog/models",
            "include_prefixes": ["qwen", "wan"],
        }

        rows = briefing._parse_qwen_model_changelog(soup, config, 5)

        self.assertEqual(len(rows), 1)
        self.assertIn("qwen-test-32b", rows[0]["title"])
        self.assertEqual(rows[0]["published_at"], "2026-08-12T00:00:00+00:00")
        self.assertTrue(rows[0]["official"])

    def test_official_x_search_groups_are_cn_first_and_bounded(self):
        briefing = DailyBriefing(dry_run=True)

        groups = briefing.official_x_search_groups(group_size=3)

        self.assertGreater(len(groups), 1)
        self.assertEqual(groups[0]["country"], "CN")
        self.assertTrue(all(group["account_count"] <= 3 for group in groups))
        self.assertTrue(all("-filter:replies" in group["query"] for group in groups))
        self.assertIn("Medo_CodeFree", {h for group in groups for h in group["handles"]})

    def test_product_and_viral_tracks_do_not_require_model_release(self):
        briefing = DailyBriefing(dry_run=True)
        item = {
            "title": "Creator tool launches a new video workflow",
            "summary": "The product update adds an API and collaborative editing.",
            "category": "产品发布/更新",
            "source": "Official Product Blog",
            "section": "ai",
            "section_name": "AI 热点",
            "overall_score": 88,
            "content_score": 90,
            "timeliness_score": 96,
            "credibility_score": 94,
            "official": True,
        }

        self.assertEqual(len(briefing.generate_product_updates([item])), 1)
        self.assertEqual(len(briefing.generate_viral_ai_news([item])), 1)

    def test_product_updates_exclude_non_ai_crypto_items(self):
        briefing = DailyBriefing(dry_run=True)
        item = {
            "title": "Crypto wallet launches a trading workflow",
            "summary": "The product adds an AI assistant and API.",
            "section": "venture",
        }

        self.assertEqual(briefing.generate_product_updates([item]), [])

    def test_capital_events_keep_the_company_industry_layer(self):
        briefing = DailyBriefing(dry_run=True)
        item = {
            "title": "AI workflow startup raises $80M Series B",
            "summary": "The company will expand its enterprise AI workflow product.",
            "url": "https://example.com/series-b",
            "source": "Company Newsroom",
            "official": True,
            "industry_track": "capital",
            "industry_layer_hint": "downstream",
        }

        briefing._enrich_news_item(item, "venture")

        self.assertEqual(item["industry_layer"], "downstream")
        self.assertEqual(item["event_type"], "funding")
        self.assertIn("funding", item["event_types"])
        self.assertEqual(item["funding_amount"].lower(), "$80m")
        self.assertEqual(item["funding_round"].lower(), "series b")

    def test_funding_verification_requires_official_or_multiple_sources(self):
        briefing = DailyBriefing(dry_run=True)
        unverified = {
            "title": "AI automation startup raises $20M",
            "summary": "The AI workflow company announced a funding round.",
            "url": "https://example.com/media-only",
            "source": "Industry Media",
        }
        verified = {
            "title": "AI coding startup raises $30M Series A",
            "summary": "The company raised capital for its enterprise AI coding product.",
            "url": "https://example.com/company",
            "source": "Company Newsroom",
            "official": True,
        }
        for item in (unverified, verified):
            briefing._enrich_news_item(item, "venture")

        entries = briefing.generate_ai_funding([unverified, verified])
        by_title = {entry["title"]: entry for entry in entries}

        self.assertEqual(
            by_title["AI automation startup raises $20M"]["funding_verification"],
            "待官方复核",
        )
        self.assertTrue(
            by_title["AI automation startup raises $20M"][
                "requires_primary_confirmation"
            ]
        )
        self.assertEqual(
            by_title["AI coding startup raises $30M Series A"]["funding_verification"],
            "已核验",
        )

    def test_industry_search_groups_are_cn_first_and_include_all_tracks(self):
        briefing = DailyBriefing(dry_run=True, lookback_hours=36)

        groups = briefing.industry_search_groups()

        self.assertEqual(groups[0]["country"], "CN")
        self.assertTrue({"applications", "capital", "infrastructure"} <= {
            group["track"] for group in groups
        })
        self.assertTrue(all("past 36 hours" in group["query"] for group in groups))

    def test_cross_layer_connections_do_not_claim_direct_causality(self):
        briefing = DailyBriefing(dry_run=True)
        upstream = {
            "title": "New inference GPU lowers enterprise AI costs",
            "summary": "The chip targets enterprise inference workloads.",
            "url": "https://example.com/gpu",
            "source": "Official Chip Blog",
            "official": True,
        }
        downstream = {
            "title": "Enterprise AI workflow expands customer deployment",
            "summary": "The agent workflow is used by enterprise customers.",
            "url": "https://example.com/workflow",
            "source": "Official Product Blog",
            "official": True,
            "industry_track": "applications",
            "industry_layer_hint": "downstream",
        }
        for item in (upstream, downstream):
            briefing._enrich_news_item(item, "ai")

        connections = briefing.generate_cross_layer_connections(
            [upstream, downstream]
        )

        self.assertGreaterEqual(len(connections), 1)
        self.assertIn("不代表", connections[0]["caveat"])

    def test_research_deployment_is_not_mislabeled_as_customer_adoption(self):
        briefing = DailyBriefing(dry_run=True)
        item = {
            "title": "Agent planning for reliable deployment",
            "summary": "A paper evaluates agent planning under partial observability.",
            "url": "https://arxiv.org/abs/example",
            "source": "arXiv",
        }

        briefing._enrich_news_item(item, "ai")

        self.assertEqual(item["event_type"], "research")
        self.assertNotIn("adoption", item["event_types"])
        self.assertEqual(item["industry_layer"], "midstream")

    def test_technical_policy_is_not_mislabeled_as_regulation(self):
        briefing = DailyBriefing(dry_run=True)
        item = {
            "title": "Agent policy optimization at test time",
            "summary": "A research paper studies a learned policy for tool use.",
            "url": "https://arxiv.org/abs/policy-example",
            "source": "arXiv",
        }

        briefing._enrich_news_item(item, "ai")

        self.assertNotIn("policy", item["event_types"])
        self.assertIn("research", item["event_types"])

    def test_customer_deployment_case_is_downstream(self):
        briefing = DailyBriefing(dry_run=True)
        item = {
            "title": "How ExampleCo deployed over 50 AI agents on AWS",
            "summary": "The company self-hosted a model and built a RAG platform.",
            "url": "https://example.com/customer-case",
            "source": "AWS Machine Learning Blog",
            "official": True,
            "industry_track": "infrastructure",
            "industry_layer_hint": "upstream",
        }

        briefing._enrich_news_item(item, "ai")

        self.assertEqual(item["event_type"], "adoption")
        self.assertEqual(item["industry_layer"], "downstream")

    def test_industry_feed_filters_corporate_culture_news(self):
        briefing = DailyBriefing(dry_run=False, history_enabled=False)
        briefing.config["editorial"]["raw_candidates"] = False
        briefing._get_content = lambda url: b"feed"
        briefing._parse_feed_articles = lambda content, source, limit: [
            {
                "title": "NVIDIA CEO Tops Glassdoor Best CEOs List",
                "summary": "An employee ranking mentions AI.",
                "url": "https://example.com/ceo-ranking",
                "source": source,
            },
            {
                "title": "NVIDIA launches new AI inference infrastructure",
                "summary": "The platform improves GPU inference throughput.",
                "url": "https://example.com/inference",
                "source": source,
            },
        ]

        rows = briefing._fetch_industry_feed(
            {
                "name": "NVIDIA Blog",
                "url": "https://example.com/feed",
                "track": "infrastructure",
                "layer_hint": "upstream",
                "authority": "official",
            },
            4,
        )

        self.assertEqual([row["title"] for row in rows], [
            "NVIDIA launches new AI inference infrastructure"
        ])

    def test_specialist_ai_infrastructure_source_keeps_gpu_analysis(self):
        briefing = DailyBriefing(dry_run=False, history_enabled=False)
        briefing._get_content = lambda url: b"feed"
        briefing._parse_feed_articles = lambda content, source, limit, max_age_days=None: [
            {
                "title": "HBM supply and GPU accelerator economics",
                "summary": "An analysis of memory bandwidth and accelerator demand.",
                "url": "https://example.com/hbm-gpu-analysis",
                "source": source,
            }
        ]

        rows = briefing._fetch_industry_feed(
            {
                "name": "SemiAnalysis",
                "url": "https://newsletter.semianalysis.com/feed",
                "track": "infrastructure",
                "layer_hint": "upstream",
                "authority": "media",
                "discovery_only": True,
                "role": "analysis",
                "priority": "high",
                "max_age_days": 21,
                "allow_ai_infrastructure_signals": True,
            },
            4,
        )

        self.assertEqual([row["title"] for row in rows], [
            "HBM supply and GPU accelerator economics"
        ])
        self.assertEqual(rows[0]["source_priority"], "high")
        self.assertEqual(rows[0]["source_role"], "analysis")

    def test_industry_feed_uses_fallback_after_transient_primary_failure(self):
        briefing = DailyBriefing(dry_run=False, history_enabled=False)
        requested = []

        def fake_get_content(url):
            requested.append(url)
            if url == "https://www.qbitai.com/feed":
                raise OSError("transient TLS failure")
            return b"feed"

        briefing._get_content = fake_get_content
        briefing._parse_feed_articles = lambda content, source, limit: [
            {
                "title": "量子位报道新的 AI 产品发布",
                "summary": "一家公司上线新的工业界 AI 产品。",
                "url": "https://www.qbitai.com/example",
                "source": source,
            }
        ]

        rows = briefing._fetch_industry_feed(
            {
                "name": "量子位",
                "url": "https://www.qbitai.com/feed",
                "fallback_urls": ["https://www.qbitai.com/rss"],
                "retries_per_url": 2,
                "track": "applications",
                "authority": "media",
            },
            4,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(requested.count("https://www.qbitai.com/feed"), 2)
        self.assertEqual(requested[-1], "https://www.qbitai.com/rss")

    def test_industry_collection_has_no_intermediate_total_cap(self):
        briefing = DailyBriefing(dry_run=False, history_enabled=False)
        briefing.config["quality"]["min_similarity_tokens"] = 100
        briefing.config["sources"]["industry_feeds"] = [
            {"name": f"source-{index}", "url": f"https://example.com/{index}"}
            for index in range(11)
        ]

        def fake_fetch(source, limit):
            return [
                {
                    "title": f"{source['name']} item {item}",
                    "url": f"{source['url']}/{item}",
                    "source": source["name"],
                }
                for item in range(limit)
            ]

        briefing._fetch_industry_feed = fake_fetch

        rows = briefing.fetch_industry_signals()

        self.assertEqual(len(rows), 44)

    def test_ecosystem_collection_has_no_intermediate_total_cap(self):
        briefing = DailyBriefing(dry_run=False, history_enabled=False)

        def rows(prefix):
            return [
                {
                    "title": f"{prefix} {index}",
                    "url": f"https://example.com/{prefix}/{index}",
                    "source": prefix,
                }
                for index in range(5)
            ]

        briefing.fetch_official_model_orgs = lambda: rows("models")
        briefing.fetch_model_changelogs = lambda: rows("changelog")
        briefing.fetch_official_x_updates = lambda: rows("x")
        briefing.fetch_official_sitemaps = lambda: rows("sitemap")
        briefing.fetch_github_releases = lambda: rows("releases")

        result = briefing.fetch_ecosystem_signals()

        self.assertEqual(len(result), 25)

    def test_non_model_github_release_prefers_product_update_event(self):
        briefing = DailyBriefing(dry_run=True)
        item = {
            "title": "agent-cli releases v2.0",
            "summary": "The update adds deployment and subscription controls.",
            "url": "https://github.com/example/agent-cli/releases/tag/v2.0",
            "source": "GitHub Release · example/agent-cli",
        }

        briefing._enrich_news_item(item, "ai")

        self.assertEqual(item["event_type"], "product_update")

    def test_model_update_is_treated_as_model_event(self):
        briefing = DailyBriefing(dry_run=True)
        item = {
            "title": "Qwen model update improves tool use",
            "source": "Qwen 官方",
        }

        briefing._mark_official_model_release(item, "模型能力更新")

        self.assertEqual(item["signal_type"], "model_release")
        self.assertEqual(item["release_kind"], "模型能力更新")

    def test_model_pricing_and_deprecation_updates_are_model_events(self):
        briefing = DailyBriefing(dry_run=True)
        cases = [
            {
                "title": "API pricing change",
                "summary": "Qwen model pricing has been reduced.",
            },
            {
                "title": "Deprecation notice",
                "summary": "The Claude model will be retired next month.",
            },
        ]

        for item in cases:
            with self.subTest(title=item["title"]):
                briefing._mark_official_model_release(item, "模型服务更新")
                self.assertEqual(item["signal_type"], "model_release")

    def test_targeted_filters_combine_mode_focus_and_hours(self):
        briefing = DailyBriefing(
            dry_run=True,
            briefing_mode="products",
            focus="医疗",
            lookback_hours=48,
        )
        briefing.config["editorial"]["raw_candidates"] = False
        recent = datetime.now(timezone.utc).isoformat()
        matching = {
            "title": "Medical AI product update launches a clinical workflow",
            "summary": "A healthcare app adds an API for doctors.",
            "published_at": recent,
            "section": "ai",
        }
        wrong_focus = {
            "title": "AI video product update launches editing tools",
            "summary": "A creator app adds an API.",
            "published_at": recent,
            "section": "ai",
        }

        self.assertTrue(briefing._matches_request(matching))
        self.assertFalse(briefing._matches_request(wrong_focus))

    def test_cli_accepts_targeted_briefing_options(self):
        args = parse_args(
            ["--mode", "models", "--focus", "AI视频", "--hours", "48"]
        )

        self.assertEqual(args.mode, "models")
        self.assertEqual(args.focus, "AI视频")
        self.assertEqual(args.hours, 48)

    def test_cli_accepts_html_output(self):
        self.assertEqual(parse_args(["--format", "html"]).format, "html")

    def test_cli_accepts_industry_application_and_funding_modes(self):
        for mode in ("industry", "applications", "funding"):
            with self.subTest(mode=mode):
                self.assertEqual(parse_args(["--mode", mode]).mode, mode)

    def test_mistral_changelog_parser_only_keeps_model_release_blocks(self):
        briefing = DailyBriefing(dry_run=True)
        briefing.config["quality"]["model_release_max_age_days"] = 0
        soup = BeautifulSoup(
            """
            <main>
              <h3>Aug 26</h3>
              <h2>August 12</h2>
              <p>We released Mistral Test (mistral-test).</p>
              <span>MODEL RELEASED</span>
              <h2>August 11</h2>
              <p>We updated the dashboard.</p>
              <span>OTHER</span>
            </main>
            """,
            "html.parser",
        )
        config = {
            "name": "Mistral AI",
            "url": "https://docs.mistral.ai/resources/changelogs",
        }

        rows = briefing._parse_mistral_model_changelog(soup, config, 5)

        self.assertEqual(len(rows), 1)
        self.assertIn("Mistral Test", rows[0]["title"])
        self.assertEqual(rows[0]["release_kind"], "模型发布")

    def test_ai_relevance_filter_removes_unrelated_venture_story(self):
        briefing = DailyBriefing(dry_run=True)

        self.assertFalse(
            briefing._is_ai_relevant(
                {
                    "title": "Nandan Nilekani launches a $200M third fund",
                    "summary": "The venture firm will back consumer startups.",
                    "source": "TechCrunch",
                }
            )
        )
        self.assertTrue(
            briefing._is_ai_relevant(
                {
                    "title": "Ollama raises $65M for its open source AI developer tool",
                    "summary": "The company is building local model tooling.",
                    "source": "TechCrunch",
                }
            )
        )

    def test_similar_news_titles_are_clustered_with_related_link(self):
        briefing = DailyBriefing(dry_run=True)
        rows = briefing._dedupe_items(
            [
                {
                    "title": "OpenAI launches new agent tools for developers",
                    "url": "https://official.example.com/agent-tools",
                    "source": "OpenAI",
                    "summary": "Official announcement.",
                },
                {
                    "title": "OpenAI launches new agent tools for developers today",
                    "url": "https://media.example.com/openai-agent-tools",
                    "source": "Tech Media",
                    "summary": "Media report.",
                },
            ]
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "OpenAI / Tech Media")
        self.assertEqual(len(rows[0]["related_links"]), 1)

    def test_same_product_event_clusters_media_and_official_wording(self):
        briefing = DailyBriefing(dry_run=True)
        media = {
            "title": "OpenAI says GPT 5.6 is the preferred model for Microsoft Copilot 365 amid breakup chatter",
            "url": "https://media.example.com/gpt-copilot",
            "source": "Tech Media",
        }
        official = {
            "title": "GPT-5.6 is now the preferred model in Microsoft 365 Copilot",
            "url": "https://official.example.com/gpt-copilot",
            "source": "OpenAI",
        }

        self.assertTrue(briefing._items_duplicate(media, official))
        self.assertFalse(
            briefing._items_duplicate(
                {
                    "title": "OpenAI launches GPT-5.6",
                    "url": "https://media.example.com/gpt-launch",
                },
                official,
            )
        )

    def test_cross_section_dedup_uses_best_matching_section(self):
        briefing = DailyBriefing(dry_run=True)
        ai_item = {
            "title": "Startup raises a new $200M venture fund",
            "url": "https://example.com/fund?utm_source=newsletter",
            "source": "TechCrunch",
            "summary": "A venture capital fundraising story.",
        }
        venture_item = {
            "title": "Startup raises a new $200M venture fund",
            "url": "https://example.com/fund",
            "source": "Venture Media",
            "summary": "A venture capital fundraising story.",
        }

        sections = briefing._dedupe_news_sections([ai_item], [venture_item])

        self.assertEqual(sections["ai"], [])
        self.assertEqual(len(sections["venture"]), 1)
        self.assertEqual(
            sections["venture"][0]["source"],
            "Venture Media / TechCrunch",
        )

    def test_round_robin_keeps_source_diversity(self):
        briefing = DailyBriefing(dry_run=True)
        groups = [
            [{"source": "Media", "title": f"M{index}"} for index in range(3)],
            [{"source": "Official", "title": f"O{index}"} for index in range(3)],
        ]

        rows = briefing._round_robin(groups, 4)

        self.assertEqual(
            [row["source"] for row in rows],
            ["Media", "Official", "Media", "Official"],
        )

    def test_save_output_creates_expected_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_output("hello", "markdown", tmpdir)

            self.assertEqual(path.suffix, ".md")
            self.assertEqual(path.read_text(encoding="utf-8"), "hello")

    def test_save_output_creates_html_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_output("<!doctype html>", "html", tmpdir)

            self.assertEqual(path.suffix, ".html")
            self.assertEqual(path.read_text(encoding="utf-8"), "<!doctype html>")

    def test_industry_profile_keeps_creator_sections_disabled(self):
        briefing = DailyBriefing(dry_run=True)
        briefing.config["editorial"]["raw_candidates"] = False
        briefing.config["limits"]["x_topics"] = 5
        briefing.config["limits"]["x_drafts"] = 3
        data = self.generate_quietly(briefing)

        formats = [draft["format"] for draft in data["sections"]["x_drafts"]]

        self.assertEqual(formats, [])

    def test_source_tiers_distinguish_official_multi_and_aggregated(self):
        briefing = DailyBriefing(dry_run=True)
        official = briefing._source_profile({"source": "OpenAI"})
        multi = briefing._source_profile(
            {
                "source": "TechCrunch / Reuters",
                "related_links": [],
            }
        )
        trending = briefing._source_profile(
            {"source": "Hugging Face Trending"}
        )

        self.assertEqual(official["verification"], "官方确认")
        self.assertEqual(multi["verification"], "多源印证")
        self.assertEqual(multi["source_count"], 2)
        self.assertEqual(trending["verification"], "单源信号")
        self.assertLess(trending["credibility_score"], official["credibility_score"])

    def test_same_publisher_feeds_do_not_count_as_multiple_sources(self):
        briefing = DailyBriefing(dry_run=True)

        profile = briefing._source_profile(
            {
                "source": "TechCrunch / TechCrunch Venture RSS",
                "related_links": [],
            }
        )

        self.assertEqual(profile["source_count"], 1)
        self.assertEqual(profile["verification"], "单源信号")

    def test_history_store_tracks_cross_day_rank_without_rerun_inflation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = BriefingStore(str(Path(tmpdir) / "history.sqlite3"))
            day_one_item = {
                "item_key": "https://example.com/agent",
                "display_title": "Agent update",
                "url": "https://example.com/agent",
                "section": "ai",
                "source": "Sample",
                "overall_score": 78,
                "source_count": 1,
            }
            store.annotate_items([day_one_item], "2026-07-12")
            self.assertEqual(day_one_item["history_status"], "首次出现")
            store.record_items([day_one_item], "2026-07-12")
            store.record_items([day_one_item], "2026-07-12")
            same_day_item = dict(day_one_item)
            store.annotate_items([same_day_item], "2026-07-12")
            self.assertEqual(same_day_item["history_status"], "首次出现")
            self.assertEqual(same_day_item["repeat_count"], 0)

            day_two_item = dict(day_one_item)
            day_two_item.update({"overall_score": 86, "source_count": 2})
            store.annotate_items([day_two_item], "2026-07-13")
            store.record_items([day_two_item], "2026-07-13")

            self.assertEqual(day_two_item["repeat_count"], 1)
            self.assertEqual(day_two_item["history_status"], "持续升温")
            self.assertEqual(day_two_item["score_delta"], 8)
            history = store.rank_history(day_two_item["item_key"])
            self.assertEqual(len(history), 2)
            self.assertEqual([row["rank"] for row in history], [1, 1])

    def test_aihot_parser_uses_current_server_rendered_cards(self):
        briefing = DailyBriefing(dry_run=False, history_enabled=False)
        html = """
        <article>
          <h3>OpenAI 发布新的开发者功能</h3>
          <p>面向开发者的真实更新。</p>
          <img alt="TechInAsia" />
        </article>
        """
        briefing._get_soup = lambda url: BeautifulSoup(html, "html.parser")

        rows = briefing.fetch_aihot(limit=1)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "AI HOT · TechInAsia")
        self.assertIn("item=", rows[0]["url"])

    def test_hn_and_huggingface_api_parsers_keep_ranking_signals(self):
        briefing = DailyBriefing(dry_run=False, history_enabled=False)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        def fake_json(url, params=None):
            if "algolia" in url:
                return {
                    "hits": [
                        {
                            "title": "AI agent workflow release",
                            "url": "https://example.com/agent-release",
                            "points": 128,
                            "num_comments": 42,
                            "created_at": now,
                            "objectID": "123",
                        }
                    ]
                }
            return [
                {
                    "id": "sample/model",
                    "pipeline_tag": "text-generation",
                    "likes": 88,
                    "trendingScore": 123,
                    "createdAt": now,
                }
            ]

        briefing._get_json = fake_json
        hn_rows = briefing.fetch_hacker_news(limit=1)
        hf_rows = briefing.fetch_huggingface_models(limit=1)

        self.assertEqual(hn_rows[0]["popularity"], 128)
        self.assertIn("42 条讨论", hn_rows[0]["summary"])
        self.assertEqual(hf_rows[0]["popularity"], 123)
        self.assertEqual(hf_rows[0]["source"], "Hugging Face Trending")

    def test_editorial_queue_preserves_facts_links_and_dimensions(self):
        briefing = DailyBriefing(dry_run=True)
        data = self.generate_quietly(briefing)
        queue = data["sections"]["editorial_queue"]

        self.assertGreaterEqual(len(queue), 1)
        self.assertTrue(queue[0]["url"].startswith("http"))
        self.assertIn("raw_summary", queue[0])
        self.assertEqual(queue[0]["editorial_status"], "pending")
        self.assertNotIn("editorial_hint", queue[0])
        self.assertTrue(all("source" in item for item in queue))
        self.assertTrue(all(item["raw_summary"] for item in queue))

    def test_feedback_updates_future_ranking_with_bounded_adjustment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = BriefingStore(str(Path(tmpdir) / "feedback.sqlite3"))
            published_item = {
                "item_key": "https://example.com/published-agent",
                "display_title": "Published agent workflow",
                "url": "https://example.com/published-agent",
                "section": "ai",
                "source": "Agent Source",
                "category": "Agent / AI 编码",
                "tags": ["Agent"],
                "overall_score": 80,
                "source_count": 1,
            }
            store.record_items([published_item], "2026-08-01")
            store.record_feedback(
                published_item["item_key"],
                "published",
                created_at="2026-08-02T08:00:00+00:00",
            )

            future_item = {
                "item_key": "https://example.com/new-agent",
                "source": "Agent Source",
                "category": "Agent / AI 编码",
                "overall_score": 70,
            }
            store.apply_feedback([future_item])

            self.assertGreater(future_item["overall_score"], 70)
            self.assertLessEqual(future_item["feedback_score"], 12)
            self.assertIn("来源", future_item["feedback_reason"])
            self.assertIn("类别", future_item["feedback_reason"])

    def test_dismissed_feedback_can_lower_exact_item_score(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = BriefingStore(str(Path(tmpdir) / "feedback.sqlite3"))
            item = {
                "item_key": "https://example.com/noise",
                "display_title": "Noisy story",
                "url": "https://example.com/noise",
                "section": "ai",
                "source": "Noise Source",
                "category": "AI 行业动态",
                "overall_score": 72,
                "source_count": 1,
            }
            store.record_items([item], "2026-08-01")
            store.record_feedback(
                item["item_key"],
                "dismissed",
                created_at="2026-08-02T08:00:00+00:00",
            )
            candidate = dict(item)
            store.apply_feedback([candidate])

            self.assertLess(candidate["overall_score"], 72)
            self.assertGreaterEqual(candidate["feedback_score"], -12)

    def test_weekly_review_combines_items_feedback_and_source_health(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = BriefingStore(str(Path(tmpdir) / "weekly.sqlite3"))
            item = {
                "item_key": "https://example.com/weekly-agent",
                "display_title": "Weekly agent update",
                "url": "https://example.com/weekly-agent",
                "section": "ai",
                "source": "OpenAI",
                "category": "Agent / AI 编码",
                "overall_score": 84,
                "source_count": 1,
            }
            store.record_items([item], "2026-08-02", [item["item_key"]])
            item["overall_score"] = 87
            store.record_items([item], "2026-08-03", [item["item_key"]])
            store.record_feedback(
                item["item_key"],
                "saved",
                created_at="2026-08-03T09:00:00+00:00",
            )
            store.record_source_runs(
                "2026-08-02",
                [
                    {
                        "source": "OpenAI",
                        "status": "ok",
                        "item_count": 3,
                        "latency_ms": 120,
                    }
                ],
            )
            store.record_source_runs(
                "2026-08-03",
                [
                    {
                        "source": "OpenAI",
                        "status": "error",
                        "item_count": 0,
                        "error": "timeout",
                        "latency_ms": 500,
                    }
                ],
            )

            summary = store.weekly_summary(days=7, end_date="2026-08-08")
            briefing = DailyBriefing(dry_run=True)
            review = {
                "metadata": {
                    "title": "Rion AI 简报周复盘",
                    "generated_at": "2026-08-08T10:00:00",
                },
                **summary,
            }
            markdown = briefing.format_weekly_review(review, "markdown")

            self.assertEqual(summary["top_items"][0]["days_seen"], 2)
            self.assertEqual(summary["feedback"]["saved"], 1)
            self.assertEqual(summary["source_health"][0]["success_rate"], 50)
            self.assertIn("## 来源健康度", markdown)
            self.assertIn("检查不稳定来源：OpenAI", markdown)

    def test_existing_history_database_is_migrated_in_place(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    """
                    CREATE TABLE items (
                        item_key TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        url TEXT NOT NULL DEFAULT '',
                        section TEXT NOT NULL DEFAULT '',
                        source TEXT NOT NULL DEFAULT '',
                        first_seen TEXT NOT NULL,
                        last_seen TEXT NOT NULL,
                        seen_count INTEGER NOT NULL DEFAULT 1,
                        selected_count INTEGER NOT NULL DEFAULT 0,
                        last_score INTEGER NOT NULL DEFAULT 0,
                        source_count INTEGER NOT NULL DEFAULT 1
                    )
                    """
                )

            BriefingStore(str(path))

            with sqlite3.connect(path) as connection:
                item_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(items)")
                }
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            self.assertTrue({"category", "tags_json", "signals_json"} <= item_columns)
            self.assertTrue({"feedback", "source_runs"} <= tables)


if __name__ == "__main__":
    unittest.main()

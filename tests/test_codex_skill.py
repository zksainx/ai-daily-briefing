import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "daily-briefing"


class CodexSkillTests(unittest.TestCase):
    def setUp(self):
        self.environment = dict(os.environ, BRIEFING_PYTHON=sys.executable)

    def test_skill_has_codex_metadata(self):
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        metadata = (SKILL_DIR / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )

        self.assertTrue(skill.startswith("---\nname: daily-briefing\n"))
        self.assertIn("Generate a source-linked Chinese AI industry", skill)
        self.assertIn("Do not use a personal profile", skill)
        self.assertIn("概述", metadata)
        self.assertIn("技术总结", metadata)
        self.assertIn("$daily-briefing", metadata)

    def test_runner_is_portable(self):
        runner = SKILL_DIR / "scripts" / "run-daily-briefing.sh"
        source = runner.read_text(encoding="utf-8")

        self.assertTrue(os.access(runner, os.X_OK))
        self.assertNotIn("/Users/rion", source)
        self.assertIn("DAILY_BRIEFING_PROJECT", source)
        self.assertNotIn("git clone", source)

    def test_runner_generates_markdown_in_dry_run(self):
        runner = SKILL_DIR / "scripts" / "run-daily-briefing.sh"
        result = subprocess.run(
            ["bash", str(runner), "--dry-run", "--no-save"],
            cwd=ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("# 原始候选采集", result.stdout)
        self.assertIn("等待编辑逐条判断并选择 Top 10", result.stdout)
        self.assertIn("](", result.stdout)

    def test_runner_supports_targeted_briefings(self):
        runner = SKILL_DIR / "scripts" / "run-daily-briefing.sh"
        result = subprocess.run(
            [
                "bash",
                str(runner),
                "--dry-run",
                "--no-save",
                "--mode",
                "hotspots",
                "--focus",
                "Agent",
                "--hours",
                "48",
            ],
            cwd=ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("# 原始候选采集", result.stdout)
        self.assertIn("AI agent", result.stdout)

    def test_runner_supports_industry_briefing(self):
        runner = SKILL_DIR / "scripts" / "run-daily-briefing.sh"
        result = subprocess.run(
            [
                "bash",
                str(runner),
                "--dry-run",
                "--no-save",
                "--mode",
                "industry",
            ],
            cwd=ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("# 原始候选采集", result.stdout)
        self.assertIn("AI workflow startup", result.stdout)

    def test_markdown_to_html_renderer_is_portable(self):
        renderer = SKILL_DIR / "scripts" / "render-briefing-html.py"
        source = renderer.read_text(encoding="utf-8")

        self.assertTrue(os.access(renderer, os.X_OK))
        self.assertNotIn("/Users/rion", source)
        self.assertIn("ai_daily_briefing.html", source)
        self.assertIn("DAILY_BRIEFING_PROJECT", source)

        with tempfile.TemporaryDirectory() as tmpdir:
            markdown = Path(tmpdir) / "briefing.md"
            output = Path(tmpdir) / "briefing.html"
            markdown.write_text(
                "# AI 简报\n\n## 今日必须看\n\n"
                "1. [官方更新](https://example.com)\n\n"
                "   示例公司发布了新功能。\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(renderer),
                    str(markdown),
                    "--output-file",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.is_file())
            self.assertIn("briefing-search", output.read_text(encoding="utf-8"))

    def test_summary_validator_accepts_specific_chinese_explanation(self):
        validator = SKILL_DIR / "scripts" / "validate-briefing.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            markdown = Path(tmpdir) / "briefing.md"
            markdown.write_text(
                "# 简报\n\n"
                "1. [Claude Code 更新](https://example.com/release)\n"
                "   Anthropic 修复了 MCP OAuth 重定向错误，Slack 等预注册客户端可以恢复登录。\n"
                "   `官方确认`\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["python3", str(validator), str(markdown)],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("检查通过", result.stdout)

    def test_summary_validator_rejects_missing_or_generic_explanation(self):
        validator = SKILL_DIR / "scripts" / "validate-briefing.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            markdown = Path(tmpdir) / "briefing.md"
            markdown.write_text(
                "# 简报\n\n"
                "1. [产品更新](https://example.com/product)\n"
                "   来源：示例公司\n\n"
                "2. [行业新闻](https://example.com/news)\n"
                "   这条围绕行业新闻展开，可作为 AI 行业观察。\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["python3", str(validator), str(markdown)],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("只有元数据", result.stderr)
        self.assertIn("过于空泛", result.stderr)


if __name__ == "__main__":
    unittest.main()

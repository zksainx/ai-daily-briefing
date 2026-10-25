"""Exercise public commands after moving business modules into a package."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class EntrypointTests(unittest.TestCase):
    def run_command(self, *args, cwd=ROOT, env=None):
        result = subprocess.run(
            [sys.executable, *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_package_entrypoint_collects_json_without_saving(self):
        result = self.run_command(
            "-m", "ai_daily_briefing", "--dry-run", "--no-save", "--editorial-packet"
        )
        packet = json.loads(result.stdout)
        self.assertTrue(packet["sections"]["editorial_queue"])
        self.assertIn("metadata", packet)

    def test_launchagent_script_works_from_an_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            environment = dict(
                os.environ,
                BRIEFING_STATE_ROOT=str(Path(tmpdir) / "runs"),
                BRIEFING_LOG_ROOT=str(Path(tmpdir) / "logs"),
                BRIEFING_OUTPUT_ROOT=str(Path(tmpdir) / "outputs"),
            )
            result = self.run_command(
                str(ROOT / "scripts/scheduled_briefing.py"),
                "--check",
                cwd=tmpdir,
                env=environment,
            )
            self.assertIn(f"state_root={tmpdir}/runs", result.stdout)
            self.assertEqual(list(Path(tmpdir).iterdir()), [])

    def test_email_script_renders_from_an_unrelated_directory_without_sending(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            markdown = directory / "briefing.md"
            markdown.write_text(
                "# AI 日报 · 2026-10-25\n\n## 本日十条行业信号\n\n"
                "1. [模型发布](https://example.com/model)\n\n"
                "   概述：公司发布了模型。用户可通过 API 使用。\n\n"
                "   技术总结：模型支持图像输入。接口支持流式输出。\n\n"
                "   来源：公司官网\n",
                encoding="utf-8",
            )
            recipients = directory / "recipients.txt"
            recipients.write_text("test@example.com\n", encoding="utf-8")
            environment = directory / "email.env"
            environment.write_text("", encoding="utf-8")
            preview = directory / "preview.html"
            result = self.run_command(
                str(ROOT / "scripts/send_briefing_email.py"),
                "--markdown", str(markdown),
                "--recipients", str(recipients),
                "--env-file", str(environment),
                "--preview", str(preview),
                cwd=tmpdir,
            )
            self.assertIn("Dry run only", result.stdout)
            self.assertIn("AI前沿日报｜2026-10-25", result.stdout)
            self.assertIn("模型发布", preview.read_text(encoding="utf-8"))

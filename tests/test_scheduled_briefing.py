import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from scripts import scheduled_briefing as runner


class ScheduledBriefingTests(unittest.TestCase):
    def test_date_range_includes_every_missing_day(self):
        self.assertEqual(
            runner.date_range("2026-09-18", "2026-09-20"),
            ["2026-09-18", "2026-09-19", "2026-09-20"],
        )

    def test_retry_schedule_is_10_30_60_then_exhausted(self):
        now = datetime(2026, 9, 19, 1, 0, tzinfo=runner.TIMEZONE)
        state = {"stages": {}}
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            runner, "STATE_ROOT", Path(tmpdir)
        ):
            for failure, delay in enumerate((10, 30, 60), 1):
                runner.record_stage_failure(
                    "2026-09-18", state, "selection", now, "network error"
                )
                stage = state["stages"]["selection"]
                self.assertEqual(stage["failures_today"], failure)
                self.assertEqual(
                    datetime.fromisoformat(stage["next_retry_at"]),
                    now + timedelta(minutes=delay),
                )
                now = datetime.fromisoformat(stage["next_retry_at"])

            runner.record_stage_failure(
                "2026-09-18", state, "selection", now, "network error"
            )
            stage = state["stages"]["selection"]
            self.assertEqual(stage["failures_today"], 4)
            self.assertNotIn("next_retry_at", stage)
            self.assertEqual(stage["exhausted_for_day"], "2026-09-19")

    def test_selection_requires_exactly_30_unique_known_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            packet = directory / "candidates.json"
            selection = directory / "selection.json"
            packet.write_text(
                json.dumps(
                    {
                        "report_date": "2026-09-18",
                        "candidates": [
                            {"candidate_id": value, "title": str(value)}
                            for value in range(1, 41)
                        ],
                    }
                ),
                encoding="utf-8",
            )
            selection.write_text(
                json.dumps({"selected_candidate_ids": list(range(1, 31))}),
                encoding="utf-8",
            )
            self.assertTrue(runner.selection_is_valid(selection, packet))

            selection.write_text(
                json.dumps({"selected_candidate_ids": [1] * 30}),
                encoding="utf-8",
            )
            self.assertFalse(runner.selection_is_valid(selection, packet))

    def test_selection_prompt_requires_prior_day_change_for_repeats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            packet = directory / "candidates.json"
            packet.write_text(
                json.dumps(
                    {
                        "report_date": "2026-09-19",
                        "candidates": [
                            {"candidate_id": value, "title": str(value)}
                            for value in range(1, 41)
                        ],
                    }
                ),
                encoding="utf-8",
            )
            previous = runner.OUTPUT_ROOT
            try:
                with patch.object(runner, "OUTPUT_ROOT", directory):
                    (directory / "briefing_2026-09-18.md").write_text(
                        "# previous\n", encoding="utf-8"
                    )
                    with patch.object(runner, "run_codex") as run_codex:
                        def fake_run(command, prompt, log, timeout):
                            response = directory / "selection-response.json"
                            response.write_text(
                                json.dumps({"selected_candidate_ids": list(range(1, 31))}),
                                encoding="utf-8",
                            )
                        run_codex.side_effect = fake_run
                        runner.run_selection("2026-09-19", directory, 1)
                        prompt = run_codex.call_args.args[1]
            finally:
                runner.OUTPUT_ROOT = previous
        self.assertIn("Prior-day items are excluded by default", prompt)
        self.assertIn("new version, new availability", prompt)

    def test_persistent_artifacts_allow_resume_without_recollection(self):
        day = "2026-09-18"
        now = datetime(2026, 9, 19, 2, 0, tzinfo=runner.TIMEZONE)
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            state_root = base / "state"
            output_root = base / "outputs"
            directory = state_root / day
            directory.mkdir(parents=True)
            candidates = [
                {"candidate_id": value, "title": f"candidate {value}"}
                for value in range(1, 41)
            ]
            (directory / "candidates.json").write_text(
                json.dumps({"report_date": day, "candidates": candidates}),
                encoding="utf-8",
            )
            selected = list(range(1, 31))
            (directory / "selection.json").write_text(
                json.dumps({"selected_candidate_ids": selected}),
                encoding="utf-8",
            )
            (directory / "shortlist.json").write_text(
                json.dumps(
                    {
                        "report_date": day,
                        "candidates": candidates[:30],
                    }
                ),
                encoding="utf-8",
            )

            def fake_verification(_day, run_directory, _attempt):
                (run_directory / f"briefing_{day}.draft.md").write_text(
                    f"# AI 工业界前沿简报 · {day}\n\n## 本日十条行业信号\n\n"
                    "1. [title](https://example.com)\n"
                    "   概述：公司发布了新的企业模型。该模型已经通过 API 开放。\n\n"
                    "   技术总结：模型支持统一多模态输入。接口支持流式输出。\n\n"
                    "   来源：公司官网｜发布日期：2026-09-18｜置信度：高\n",
                    encoding="utf-8",
                )

            with (
                patch.object(runner, "STATE_ROOT", state_root),
                patch.object(runner, "OUTPUT_ROOT", output_root),
                patch.object(runner, "collect_candidates") as collect,
                patch.object(runner, "run_selection") as select,
                patch.object(runner, "run_verification", side_effect=fake_verification),
                patch.object(runner, "validate_draft"),
            ):
                result = runner.process_day(day, now, no_send=True)

            self.assertEqual(result, "ready")
            collect.assert_not_called()
            select.assert_not_called()
            self.assertTrue((output_root / f"briefing_{day}.md").is_file())

    def test_validator_requires_two_structured_paragraphs(self):
        day = "2026-09-18"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "briefing.md"
            path.write_text(
                f"# AI 工业界前沿简报 · {day}\n\n## 本日十条行业信号\n\n"
                "1. [title](https://example.com)\n"
                "   概述：公司发布了新的企业模型。该模型已经通过 API 开放。\n\n"
                "   来源：公司官网｜发布日期：2026-09-18｜置信度：高\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "概述、技术总结"):
                runner.validate_draft(path, day)


if __name__ == "__main__":
    unittest.main()

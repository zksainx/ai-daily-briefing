import tempfile
import unittest
from datetime import date
from pathlib import Path

from ai_daily_briefing.retention import (
    expired_reports, load_retention_days, prune_reports,
)


class ReportRetentionTests(unittest.TestCase):
    def test_calendar_boundary_and_supplements_ignore_modification_time(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            outputs = root / "outputs"
            outputs.mkdir()
            old_names = (
                "briefing_2026-09-25.md",
                "briefing_2026-09-25_supplement.html",
                "candidates_2026-09-01.json",
                "editorial_packet_2026-09-01.json",
                "weekly_review_2026-09-01.txt",
            )
            kept_names = (
                "briefing_2026-09-26.md",
                "briefing_2026-10-25.md",
                "briefing_2026-10-26.md",
                "briefing_2026-02-30.md",
                "notes_2026-09-01.md",
                "email-state.json",
                "briefing_undated.md",
            )
            for name in old_names + kept_names:
                (outputs / name).write_text("report", encoding="utf-8")
            root_report = root / "briefing_2026-09-01.md"
            root_report.write_text("legacy root report", encoding="utf-8")
            removed = prune_reports(root, outputs, today=date(2026, 10, 25))
            self.assertEqual(
                set(removed), {outputs / n for n in old_names} | {root_report}
            )
            self.assertEqual({p.name for p in outputs.iterdir()}, set(kept_names))
            self.assertEqual(prune_reports(root, outputs, today=date(2026, 10, 25)), [])

    def test_never_follows_symlinks_or_cleans_external_outputs_or_nested_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve() / "repo"
            outputs = root / "outputs"
            outputs.mkdir(parents=True)
            external = Path(tmpdir).resolve() / "external"
            external.mkdir()
            external_report = external / "briefing_2026-09-01.md"
            external_report.write_text("keep", encoding="utf-8")
            symlink = outputs / external_report.name
            symlink.symlink_to(external_report)
            nested = outputs / "state"
            nested.mkdir()
            nested_report = nested / external_report.name
            nested_report.write_text("keep", encoding="utf-8")
            for directory in (outputs, external):
                self.assertEqual(
                    prune_reports(root, directory, today=date(2026, 10, 25)), []
                )
            linked_outputs = root / "linked-outputs"
            linked_outputs.symlink_to(external, target_is_directory=True)
            self.assertEqual(
                prune_reports(root, linked_outputs, today=date(2026, 10, 25)), []
            )
            self.assertTrue(external_report.is_file())
            self.assertTrue(symlink.is_symlink())
            self.assertTrue(nested_report.is_file())

    def test_configurable_retention_and_invalid_settings_do_not_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            config = root / "config.yaml"
            self.assertEqual(load_retention_days(config), 30)
            config.write_text("output:\n  retention_days: 7\n", encoding="utf-8")
            report = root / "briefing_2026-10-18.md"
            report.write_text("report", encoding="utf-8")
            self.assertEqual(
                expired_reports(
                    root, root, today=date(2026, 10, 25), retention_days=7
                ),
                [report],
            )
            self.assertEqual(load_retention_days(config), 7)
            for value in (0, -1, True, "30"):
                with self.assertRaises(ValueError):
                    prune_reports(root, root, retention_days=value)
            self.assertTrue(report.exists())

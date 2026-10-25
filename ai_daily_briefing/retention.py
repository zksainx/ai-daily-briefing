"""Expire dated report files inside the project, without touching run state."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import yaml


DEFAULT_RETENTION_DAYS = 30
REPORT_NAME = re.compile(
    r"(?:briefing|candidates|editorial_packet|weekly_review)_"
    r"(?P<day>\d{4}-\d{2}-\d{2})(?:_[A-Za-z0-9_-]+)?\.(?:md|html|txt|json)"
)


def retention_days_from_config(config: dict) -> int:
    value = config.get("output", {}).get("retention_days", DEFAULT_RETENTION_DAYS)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("output.retention_days must be a positive integer")
    return value


def load_retention_days(config_path: Path) -> int:
    if not config_path.exists():
        return DEFAULT_RETENTION_DAYS
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return retention_days_from_config(config)


def expired_reports(
    project_root: Path,
    output_root: Path,
    *,
    today: date | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> list[Path]:
    """Find recognized reports older than N calendar days, including today.

    Inspect only the project root and its output directory, without recursion.
    Dates come from filenames, so copying an old report cannot reset its age.
    Never follow symlinks or inspect a configured output directory outside the repo.
    """
    retention_days_from_config({"output": {"retention_days": retention_days}})
    today = today or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    cutoff = today - timedelta(days=retention_days - 1)
    root = project_root.resolve()
    directories = {root}
    if not output_root.is_symlink() and output_root.resolve().is_relative_to(root):
        directories.add(output_root.resolve())
    expired = []
    for directory in sorted(directories):
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            match = REPORT_NAME.fullmatch(path.name)
            if not match or path.is_symlink() or not path.is_file():
                continue
            try:
                report_day = date.fromisoformat(match["day"])
            except ValueError:
                continue
            if report_day < cutoff:
                expired.append(path)
    return expired


def prune_reports(
    project_root: Path,
    output_root: Path,
    *,
    today: date | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> list[Path]:
    removed = []
    for path in expired_reports(
        project_root, output_root, today=today, retention_days=retention_days
    ):
        path.unlink(missing_ok=True)
        removed.append(path)
    return removed

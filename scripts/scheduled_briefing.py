#!/usr/bin/env python3
"""Stable entrypoint retained for the installed macOS LaunchAgent."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_daily_briefing.workflow import main


if __name__ == "__main__":
    raise SystemExit(main())

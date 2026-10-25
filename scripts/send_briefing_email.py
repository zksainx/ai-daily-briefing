#!/usr/bin/env python3
"""Command-line entrypoint for briefing email previews and delivery."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_daily_briefing.delivery import main


if __name__ == "__main__":
    raise SystemExit(main())

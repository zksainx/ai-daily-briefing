#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
EMBEDDED_REPO="$(cd "$SKILL_DIR/../.." && pwd -P)"

find_project() {
  if [ -n "${DAILY_BRIEFING_PROJECT:-}" ] && [ -f "$DAILY_BRIEFING_PROJECT/ai_daily_briefing/collector.py" ]; then
    printf '%s\n' "$DAILY_BRIEFING_PROJECT"
    return
  fi

  if [ -f "$PWD/ai_daily_briefing/collector.py" ] && [ -f "$PWD/config.yaml" ]; then
    printf '%s\n' "$PWD"
    return
  fi

  if [ -f "$EMBEDDED_REPO/ai_daily_briefing/collector.py" ]; then
    printf '%s\n' "$EMBEDDED_REPO"
    return
  fi

  echo "找不到本地 ai-daily-briefing 项目，请设置 DAILY_BRIEFING_PROJECT。" >&2
  return 1
}

PROJECT_DIR="$(find_project)"
PYTHON_BIN="${BRIEFING_PYTHON:-$PROJECT_DIR/.venv/bin/python}"

cd "$PROJECT_DIR"

if [ ! -x "$PYTHON_BIN" ]; then
  python3 -m venv .venv
  "$PYTHON_BIN" -m pip install -r requirements.txt
fi

if [ "$#" -eq 0 ]; then
  set -- --format markdown
fi

exec "$PYTHON_BIN" -m ai_daily_briefing "$@"

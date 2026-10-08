#!/usr/bin/env python3
"""Recoverable two-stage generator for the daily AI industry briefing."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from zoneinfo import ZoneInfo

import yaml


ROOT = Path(__file__).resolve().parents[1]
CODEX = Path(
    os.environ.get(
        "BRIEFING_CODEX",
        "/Users/kxzhang/.nvm/versions/node/v22.17.1/bin/codex",
    )
)
TIMEZONE = ZoneInfo("Asia/Shanghai")
STATE_ROOT = Path(
    os.environ.get(
        "BRIEFING_STATE_ROOT",
        str(Path.home() / "Library" / "Application Support" / "ai-daily-briefing" / "runs"),
    )
)
LOG_ROOT = Path(
    os.environ.get(
        "BRIEFING_LOG_ROOT",
        str(Path.home() / "Library" / "Logs" / "ai-daily-briefing"),
    )
)
OUTPUT_ROOT = Path(os.environ.get("BRIEFING_OUTPUT_ROOT", str(ROOT / "outputs")))
RECIPIENTS = Path(
    os.environ.get("BRIEFING_RECIPIENTS", str(ROOT / "email" / "recipients.txt"))
)
EMAIL_LEDGER = Path(
    os.environ.get("BRIEFING_EMAIL_LEDGER", str(LOG_ROOT / "email-state.json"))
)
sys.path.insert(0, str(ROOT))


def load_pipeline_limits() -> dict[str, int]:
    defaults = {
        "candidate_pool_max": 80,
        "shortlist_size": 30,
        "final_report_max": 10,
    }
    try:
        configured = yaml.safe_load(
            (ROOT / "config.yaml").read_text(encoding="utf-8")
        ).get("pipeline", {})
    except (OSError, AttributeError, yaml.YAMLError):
        configured = {}
    return {
        key: max(1, int(configured.get(key, default)))
        for key, default in defaults.items()
    }


START_DATE = os.environ.get("BRIEFING_START_DATE", "2026-09-18")
RETRY_DELAYS_MINUTES = (10, 30, 60)
MODEL = "gpt-5.6-terra"
REASONING_EFFORT = "xhigh"
REPORT_CUTOFF_TIME = time(hour=8)
REPORT_WINDOW_HOURS = 24
WINDOW_POLICY = "asia-shanghai-0800-v1"
PIPELINE_LIMITS = load_pipeline_limits()
MAX_CANDIDATES = PIPELINE_LIMITS["candidate_pool_max"]
SHORTLIST_SIZE = min(PIPELINE_LIMITS["shortlist_size"], MAX_CANDIDATES)
FINAL_REPORT_MAX = min(PIPELINE_LIMITS["final_report_max"], SHORTLIST_SIZE)


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def parse_published_at(value: Any) -> datetime | None:
    """Parse a source timestamp into the briefing's local time zone."""
    value = str(value or "").strip()
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(TIMEZONE)


def report_date(now: datetime) -> str:
    local_now = now.astimezone(TIMEZONE)
    latest = local_now.date()
    if local_now.timetz().replace(tzinfo=None) < REPORT_CUTOFF_TIME:
        latest -= timedelta(days=1)
    return latest.isoformat()


def scheduled_report_date(now: datetime) -> str | None:
    """Return today's report only after its 08:00 cutoff has closed."""
    local_now = now.astimezone(TIMEZONE)
    if local_now.timetz().replace(tzinfo=None) < REPORT_CUTOFF_TIME:
        return None
    return local_now.date().isoformat()


def report_window(day: str) -> tuple[datetime, datetime]:
    cutoff = datetime.combine(date.fromisoformat(day), REPORT_CUTOFF_TIME, TIMEZONE)
    return cutoff - timedelta(hours=REPORT_WINDOW_HOURS), cutoff


def window_id(day: str) -> str:
    start, cutoff = report_window(day)
    return f"{WINDOW_POLICY}:{start.isoformat()}:{cutoff.isoformat()}"


def date_range(start: str, end: str) -> list[str]:
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)
    if first > last:
        return []
    return [
        (first + timedelta(days=offset)).isoformat()
        for offset in range((last - first).days + 1)
    ]


def run_dir(day: str) -> Path:
    return STATE_ROOT / day


def state_path(day: str) -> Path:
    return run_dir(day) / "run-state.json"


def load_run_state(day: str) -> dict[str, Any]:
    value = read_json(state_path(day), {})
    if not isinstance(value, dict):
        value = {}
    value.setdefault("report_date", day)
    value.setdefault("status", "pending")
    value.setdefault("stages", {})
    return value


def save_run_state(day: str, state: dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(TIMEZONE).isoformat(timespec="seconds")
    atomic_write_json(state_path(day), state)


def stage_state(state: dict[str, Any], stage: str) -> dict[str, Any]:
    stages = state.setdefault("stages", {})
    return stages.setdefault(stage, {})


def reset_retry_window_if_needed(stage: dict[str, Any], now: datetime) -> None:
    today = now.astimezone(TIMEZONE).date().isoformat()
    if stage.get("retry_day") != today:
        stage["retry_day"] = today
        stage["failures_today"] = 0
        stage.pop("next_retry_at", None)
        stage.pop("exhausted_for_day", None)


def stage_is_due(stage: dict[str, Any], now: datetime) -> bool:
    reset_retry_window_if_needed(stage, now)
    if stage.get("exhausted_for_day"):
        return False
    next_retry = stage.get("next_retry_at")
    if not next_retry:
        return True
    try:
        return now >= datetime.fromisoformat(next_retry)
    except ValueError:
        return True


def record_stage_success(
    day: str, state: dict[str, Any], name: str, now: datetime
) -> None:
    stage = stage_state(state, name)
    stage.update(
        {
            "status": "complete",
            "completed_at": now.isoformat(timespec="seconds"),
            "failures_today": 0,
        }
    )
    stage.pop("next_retry_at", None)
    stage.pop("exhausted_for_day", None)
    stage.pop("last_error", None)
    state["status"] = f"{name}_complete"
    state.pop("last_error", None)
    save_run_state(day, state)


def record_stage_failure(
    day: str,
    state: dict[str, Any],
    name: str,
    now: datetime,
    error: str,
) -> None:
    stage = stage_state(state, name)
    reset_retry_window_if_needed(stage, now)
    failures = int(stage.get("failures_today", 0)) + 1
    stage.update(
        {
            "status": "failed",
            "failures_today": failures,
            "last_attempt_at": now.isoformat(timespec="seconds"),
            "last_error": error[-4000:],
        }
    )
    if failures <= len(RETRY_DELAYS_MINUTES):
        delay = RETRY_DELAYS_MINUTES[failures - 1]
        stage["next_retry_at"] = (now + timedelta(minutes=delay)).isoformat(
            timespec="seconds"
        )
        stage.pop("exhausted_for_day", None)
    else:
        stage.pop("next_retry_at", None)
        stage["exhausted_for_day"] = now.date().isoformat()
    state["status"] = f"{name}_failed"
    state["last_error"] = {"stage": name, "message": error[-4000:]}
    save_run_state(day, state)


def error_with_log(error: Exception, log_path: Path) -> str:
    detail = f"{type(error).__name__}: {error}"
    if log_path.is_file():
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
        if tail.strip():
            detail += "\n" + tail
    return detail


def candidate_packet_is_valid(path: Path, day: str) -> bool:
    value = read_json(path, {})
    candidates = value.get("candidates", []) if isinstance(value, dict) else []
    window_start, cutoff = report_window(day)
    return (
        value.get("report_date") == day
        and value.get("window_policy") == WINDOW_POLICY
        and value.get("window_id") == window_id(day)
        and value.get("window_start") == window_start.isoformat()
        and value.get("cutoff_at") == cutoff.isoformat()
        and isinstance(candidates, list)
        and 0 < len(candidates) <= MAX_CANDIDATES
        and all(isinstance(row, dict) and row.get("candidate_id") for row in candidates)
    )


def collect_candidates(day: str, destination: Path) -> None:
    from briefing import DailyBriefing

    window_start, cutoff = report_window(day)
    briefing = DailyBriefing(
        config_path=str(ROOT / "config.yaml"),
        history_enabled=False,
        lookback_hours=REPORT_WINDOW_HOURS,
        report_cutoff=cutoff,
    )
    data = briefing.generate_data()

    rows = []
    for row in data.get("sections", {}).get("editorial_queue", []):
        published = parse_published_at(row.get("published_at") or row.get("time"))
        if published is None or not (window_start <= published < cutoff):
            continue
        rows.append(row)
        if len(rows) >= MAX_CANDIDATES:
            break
    if not rows:
        raise RuntimeError("No candidates; refusing to publish an empty report")
    candidates = []
    for index, row in enumerate(rows, 1):
        candidate = dict(row)
        candidate["candidate_id"] = index
        published = parse_published_at(
            candidate.get("published_at") or candidate.get("time")
        )
        if published is not None:
            candidate["published_at_local"] = published.isoformat()
            candidate["published_local_date"] = published.date().isoformat()
        candidates.append(candidate)
    packet = {
        "report_date": day,
        "timezone": "Asia/Shanghai",
        "window_policy": WINDOW_POLICY,
        "window_id": window_id(day),
        "window_start": window_start.isoformat(),
        "cutoff_at": cutoff.isoformat(),
        "collected_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "source_health": getattr(briefing, "source_health", {}),
        "x_usage": getattr(briefing, "x_usage_stats", {}),
    }
    atomic_write_json(destination, packet)


def selection_is_valid(selection_path: Path, packet_path: Path) -> bool:
    selection = read_json(selection_path, {})
    packet = read_json(packet_path, {})
    candidates = packet.get("candidates", []) if isinstance(packet, dict) else []
    selected = (
        selection.get("selected_candidate_ids", [])
        if isinstance(selection, dict)
        else []
    )
    target = min(SHORTLIST_SIZE, len(candidates))
    valid_ids = {row.get("candidate_id") for row in candidates}
    return (
        selection.get("window_id") == packet.get("window_id")
        and len(selected) == target
        and len(set(selected)) == target
        and all(isinstance(value, int) and value in valid_ids for value in selected)
    )


def shortlist_is_valid(shortlist_path: Path, packet_path: Path) -> bool:
    shortlist = read_json(shortlist_path, {})
    packet = read_json(packet_path, {})
    rows = shortlist.get("candidates", []) if isinstance(shortlist, dict) else []
    target = min(
        SHORTLIST_SIZE,
        len(packet.get("candidates", [])) if isinstance(packet, dict) else 0,
    )
    return (
        shortlist.get("report_date") == packet.get("report_date")
        and shortlist.get("window_id") == packet.get("window_id")
        and len(rows) == target
        and len({row.get("candidate_id") for row in rows}) == target
    )


def build_shortlist(packet_path: Path, selection_path: Path, output_path: Path) -> None:
    packet = read_json(packet_path, {})
    selection = read_json(selection_path, {})
    selected = selection["selected_candidate_ids"]
    by_id = {row["candidate_id"]: row for row in packet["candidates"]}
    atomic_write_json(
        output_path,
        {
            "report_date": packet["report_date"],
            "window_policy": packet["window_policy"],
            "window_id": packet["window_id"],
            "window_start": packet["window_start"],
            "cutoff_at": packet["cutoff_at"],
            "selected_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
            "candidate_count": len(selected),
            "candidates": [by_id[value] for value in selected],
        },
    )


def codex_base_command(*, writable_dir: Path, web: bool) -> list[str]:
    search_mode = "live" if web else "disabled"
    return [
        str(CODEX),
        "exec",
        "-C",
        str(ROOT),
        "--model",
        MODEL,
        "-c",
        f'model_reasoning_effort="{REASONING_EFFORT}"',
        "--sandbox",
        "workspace-write" if web else "read-only",
        "-c",
        f"sandbox_workspace_write.network_access={'true' if web else 'false'}",
        "-c",
        f'web_search="{search_mode}"',
        "--ephemeral",
        "--color",
        "never",
        "--add-dir",
        str(writable_dir),
    ]


def run_codex(command: list[str], prompt: str, log_path: Path, timeout: int) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        subprocess.run(
            command + [prompt],
            check=True,
            timeout=timeout,
            stdout=log,
            stderr=subprocess.STDOUT,
        )


def run_selection(day: str, directory: Path, attempt: int) -> None:
    packet = directory / "candidates.json"
    response = directory / "selection-response.json"
    schema = directory / "selection-schema.json"
    selection = directory / "selection.json"
    shortlist = directory / "shortlist.json"
    target = min(SHORTLIST_SIZE, len(read_json(packet, {})["candidates"]))
    atomic_write_json(
        schema,
        {
            "type": "object",
            "properties": {
                "selected_candidate_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": target,
                    "maxItems": target,
                }
            },
            "required": ["selected_candidate_ids"],
            "additionalProperties": False,
        },
    )
    previous_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    previous_report = OUTPUT_ROOT / f"briefing_{previous_day}.md"
    previous_context = (
        f"The previous sent report is at {previous_report}; read it and treat its items as already sent."
        if previous_report.is_file()
        else "There is no previous sent report to compare against."
    )
    packet_data = read_json(packet, {})
    prompt = f"""You are stage 1 of an AI industry daily briefing pipeline.
Read the fixed candidate packet at {packet}. It contains at most {MAX_CANDIDATES} candidates for report date {day}. Its exact half-open window is [{packet_data['window_start']}, {packet_data['cutoff_at']}) in Asia/Shanghai: include the start instant and exclude the cutoff instant.
{previous_context}
Use each candidate's `published_at_local` for boundary decisions; `published_at` may be UTC and its date substring is not the report's Asia/Shanghai date. Select exactly {target} candidate IDs for a verification shortlist. Judge editorially; do not use keyword scoring and do not browse the web. Cover consequential company releases and changes across foundation models, multimodal, world models, embodied AI, agents, developer products, chips, data centers, cloud/inference infrastructure, adoption, and major commercial events. A first-party foundation-model, open-weight, or major API-model release inside this report window belongs in the shortlist unless it is a genuine duplicate. Exclude academic papers and purely academic research. Prefer recent, concrete and non-duplicate events from credible sources, including strong industry media and analysis such as SemiAnalysis, not only company homepages.
Events already sent in the previous report are excluded by default. Re-select one only when the candidate clearly represents a new version, new availability, a new benchmark result, or a material new development after the prior report. Different URLs or different wording for the same event do not count as new progress.
Exclude cryptocurrency and blockchain stories even when they mention AI. Do not use a personal profile, named-person preference, legacy personalization score, or feedback-derived preference adjustment. Judge industry significance, timeliness, source credibility, technical substance, and source diversity directly.
Return only the requested JSON containing selected_candidate_ids. Do not write per-candidate inclusion/exclusion reasons and do not write the final briefing."""
    command = codex_base_command(writable_dir=directory, web=False) + [
        "--output-schema",
        str(schema),
        "--output-last-message",
        str(response),
    ]
    log = directory / f"selection-attempt-{attempt}.log"
    run_codex(command, prompt, log, timeout=2700)
    parsed = json.loads(response.read_text(encoding="utf-8"))
    parsed["window_id"] = packet_data["window_id"]
    atomic_write_json(selection, parsed)
    if not selection_is_valid(selection, packet):
        raise RuntimeError(
            f"Stage 1 returned an invalid {target}-candidate selection"
        )
    build_shortlist(packet, selection, shortlist)


def initialize_verification_progress(day: str, shortlist_path: Path, path: Path) -> None:
    shortlist = read_json(shortlist_path, {})
    existing = read_json(path, {})
    if (
        isinstance(existing, dict)
        and existing.get("report_date") == day
        and existing.get("window_id") == shortlist.get("window_id")
    ):
        return
    atomic_write_json(
        path,
        {
            "report_date": day,
            "window_policy": shortlist["window_policy"],
            "window_id": shortlist["window_id"],
            "window_start": shortlist["window_start"],
            "cutoff_at": shortlist["cutoff_at"],
            "status": "pending",
            "checked_candidate_ids": [],
            "candidates": [
                {
                    "candidate_id": row["candidate_id"],
                    "status": "pending",
                    "verified_url": "",
                    "verified_publication_date": "",
                    "notes": "",
                }
                for row in shortlist["candidates"]
            ],
        },
    )


def report_window_marker(packet: dict[str, Any]) -> str:
    return f"<!-- briefing-window: {packet['window_id']} -->"


def report_matches_window(path: Path, packet_path: Path) -> bool:
    if not path.is_file():
        return False
    packet = read_json(packet_path, {})
    if not isinstance(packet, dict) or not packet.get("window_id"):
        return False
    try:
        return report_window_marker(packet) in path.read_text(encoding="utf-8")
    except OSError:
        return False


def validate_draft(
    path: Path,
    expected_day: str | None = None,
    expected_window_id: str | None = None,
) -> None:
    if not path.is_file():
        raise RuntimeError("Stage 2 did not create a Markdown draft")
    text = path.read_text(encoding="utf-8")
    first_line = text.splitlines()[0] if text.splitlines() else ""
    if expected_day and expected_day not in first_line:
        raise RuntimeError(f"Draft title does not contain report date {expected_day}")
    if expected_window_id and f"<!-- briefing-window: {expected_window_id} -->" not in text:
        raise RuntimeError("Draft does not contain the expected report-window marker")
    if "## 本日十条行业信号" not in text:
        raise RuntimeError("Draft is missing the daily Top 10 section")
    forbidden = ("入选理由", "为什么重要", "这不代表", "不能据此认为", "仍需")
    matched = next((phrase for phrase in forbidden if phrase in text), "")
    if matched:
        raise RuntimeError(f"Draft contains forbidden editorial filler: {matched}")
    count = len(re.findall(r"^\d+\. \[", text, re.MULTILINE))
    if not 1 <= count <= FINAL_REPORT_MAX:
        raise RuntimeError(
            f"Expected 1-{FINAL_REPORT_MAX} editorial items, got {count}"
        )
    blocks = re.findall(
        r"(?ms)^\d+\. \[[^\]]+\]\(https?://[^)]+\)\n(.*?)(?=^\d+\. \[|^## |\Z)",
        text,
    )
    if len(blocks) != count:
        raise RuntimeError("Could not parse every Top 10 item for format validation")
    for index, block in enumerate(blocks, 1):
        overview = re.search(r"(?m)^\s{3,}概述：\s*(\S.*)$", block)
        technical = re.search(r"(?m)^\s{3,}技术总结：\s*(\S.*)$", block)
        metadata = re.search(r"(?m)^\s{3,}来源：\s*(\S.*)$", block)
        if not overview or not technical or not metadata:
            raise RuntimeError(
                f"Item {index} must contain indented 概述、技术总结 and 来源 paragraphs"
            )
        for label, paragraph in (
            ("概述", overview.group(1)),
            ("技术总结", technical.group(1)),
        ):
            sentence_count = len(re.findall(r"[^。！？!?]+[。！？!?]", paragraph))
            if not 2 <= sentence_count <= 3:
                raise RuntimeError(
                    f"Item {index} {label} must contain 2-3 sentences, got {sentence_count}"
                )
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "skills/daily-briefing/scripts/validate-briefing.py"),
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError((result.stdout + "\n" + result.stderr).strip())


def run_verification(day: str, directory: Path, attempt: int) -> None:
    shortlist = directory / "shortlist.json"
    progress = directory / "verification-progress.json"
    draft = directory / f"briefing_{day}.draft.md"
    initialize_verification_progress(day, shortlist, progress)
    shortlist_data = read_json(shortlist, {})
    shortlist_count = len(shortlist_data.get("candidates", []))
    previous_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    previous_report = OUTPUT_ROOT / f"briefing_{previous_day}.md"
    previous_context = (
        f"The previous sent report is at {previous_report}; compare every shortlisted event against it."
        if previous_report.is_file()
        else "There is no previous sent report to compare against."
    )
    prompt = f"""You are stage 2 of a recoverable AI industry daily briefing pipeline.
Report date: {day} in Asia/Shanghai. The exact half-open candidate window is [{shortlist_data['window_start']}, {shortlist_data['cutoff_at']}): include the start instant and exclude the cutoff instant. Read only the {shortlist_count}-candidate shortlist at {shortlist}. The persistent verification state is {progress}, and the persistent Markdown draft is {draft}.
{previous_context}

Resume from the existing progress and draft only when their `window_id` matches `{shortlist_data['window_id']}`. Open original sources for shortlisted candidates, verify facts and actual publication timestamps (not sitemap modification dates), and reject anything outside the half-open window. Use other credible pages only to corroborate shortlisted events; every final item must correspond to a shortlist candidate. For sources that expose only a date, do not invent a time; keep the item only when the date cannot put it outside the window, and note the boundary uncertainty in verification state. Update {progress} in small batches while working, preserving checked_candidate_ids and concise factual notes so a later retry can continue. Do not write long selection rationales.

All boundary decisions use `published_at_local` in Asia/Shanghai; never classify an ISO timestamp by its UTC date substring.

Choose up to {FINAL_REPORT_MAX} of the strongest verified AI INDUSTRY stories across models, multimodal, world models, embodied AI, products, agents, infrastructure, adoption and commercialization. There are no category quotas: judge the full shortlist by significance, timeliness, source credibility and technical substance. Events already sent in the previous report are excluded by default. Allow a repeated event only if the verified source shows a new version, new availability, a new benchmark result, or a material new development after the previous report; a new URL or rewritten headline alone is insufficient. A material first-party foundation-model, open-weight, or major API-model release inside this report window must be included as a launch story when verified, unless it is a genuine duplicate of the prior report. Evaluate a release as its actual parent model when the candidate is a related checkpoint, distillation artifact or media coverage. Consult its official announcement or model collection for verification. Do not replace a shortlisted model-launch story with an allegation, controversy or unrelated claim found during corroboration: such a claim needs its own independently selected candidate. Do not include academic papers or purely academic research. Write the complete final Chinese Markdown to {draft}, beginning with these exact two lines:
`# AI 工业界前沿简报 · {day}`
`{report_window_marker(shortlist_data)}`
Under `## 本日十条行业信号`, every item must use this exact structure, including the three-space indentation:
Exclude cryptocurrency and blockchain stories even when they mention AI. Do not use a personal profile, named-person preference, legacy personalization score, or feedback-derived preference adjustment.

1. [标题](原始链接)
   概述：用 2-3 句说明主体、发布或变化、可用范围以及关键结果。

   技术总结：用 2-3 句说明来源明确披露的架构、接口、部署方式、实现变化或测试设置。商业或政策事件也要写其产品机制、实施流程或基础设施细节，不要编造未披露的技术。

   来源：来源名称｜发布日期：YYYY-MM-DD｜置信度：高/中高/中

Both 概述 and 技术总结 are required for every item and must be separate paragraphs. Each sentence must add a distinct fact. Include no 入选理由/为什么重要, generic editorial judgment, rebuttal-style caveats, or filler. Use fewer than {FINAL_REPORT_MAX} items if evidence is insufficient.

Run `.venv/bin/python skills/daily-briefing/scripts/validate-briefing.py {draft}` and fix the draft until it passes. Then mark {progress} status complete. Produce only this Markdown draft and progress JSON; do not send email, generate HTML, edit project code/config/skills, or collect a new candidate pool."""
    command = codex_base_command(writable_dir=directory, web=True)
    log = directory / f"verification-attempt-{attempt}.log"
    run_codex(command, prompt, log, timeout=5400)
    validate_draft(draft, day, shortlist_data["window_id"])


def mark_verification_complete(day: str, directory: Path) -> None:
    path = directory / "verification-progress.json"
    progress = read_json(path, {})
    if not isinstance(progress, dict):
        progress = {"report_date": day}
    progress["status"] = "complete"
    progress["window_id"] = read_json(directory / "shortlist.json", {}).get(
        "window_id", ""
    )
    progress["completed_at"] = datetime.now(TIMEZONE).isoformat(timespec="seconds")
    atomic_write_json(path, progress)


def email_delivery_complete(day: str) -> bool:
    from briefing_email import delivery_key, load_recipients, read_delivery_state

    recipients = load_recipients(RECIPIENTS)
    if not recipients:
        raise RuntimeError("Recipient list is empty")
    ledger = read_delivery_state(EMAIL_LEDGER)
    return all(delivery_key(day, recipient) in ledger for recipient in recipients)


def send_email(md: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/send_briefing_email.py"),
            "--markdown",
            str(md),
            "--recipients",
            str(RECIPIENTS),
            "--state-file",
            str(EMAIL_LEDGER),
            "--send",
        ],
        check=True,
        timeout=900,
    )


def process_day(day: str, now: datetime, *, no_send: bool = False) -> str:
    directory = run_dir(day)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    state = load_run_state(day)
    md = OUTPUT_ROOT / f"briefing_{day}.md"
    packet = directory / "candidates.json"
    selection = directory / "selection.json"
    shortlist = directory / "shortlist.json"
    draft = directory / f"briefing_{day}.draft.md"

    if state.get("status") in {"email_complete", "skipped"}:
        return "complete"

    stages = (
        (
            "collection",
            lambda attempt: collect_candidates(day, packet),
            lambda: candidate_packet_is_valid(packet, day),
        ),
        (
            "selection",
            lambda attempt: run_selection(day, directory, attempt),
            lambda: selection_is_valid(selection, packet)
            and shortlist_is_valid(shortlist, packet),
        ),
        (
            "verification",
            lambda attempt: run_verification(day, directory, attempt),
            lambda: report_matches_window(md, packet)
            or report_matches_window(draft, packet),
        ),
    )

    for name, action, artifact_exists in stages:
        packet_data = read_json(packet, {})
        expected_window_id = packet_data.get("window_id", "")
        if name == "verification" and report_matches_window(md, packet):
            record_stage_success(day, state, name, now)
            continue
        if name == "verification" and report_matches_window(draft, packet):
            try:
                validate_draft(draft, day, expected_window_id)
                OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
                os.replace(draft, md)
                mark_verification_complete(day, directory)
                print(f"Recovered and published {md}", flush=True)
                record_stage_success(day, state, name, datetime.now(TIMEZONE))
                continue
            except Exception:
                # Keep the partial draft in place so the next Codex attempt can
                # revise it together with the saved verification progress.
                pass
        if name != "verification" and artifact_exists():
            record_stage_success(day, state, name, now)
            continue
        stage = stage_state(state, name)
        if not stage_is_due(stage, now):
            save_run_state(day, state)
            return "waiting"
        attempt = int(stage.get("attempts_total", 0)) + 1
        stage["attempts_total"] = attempt
        stage["last_attempt_at"] = now.isoformat(timespec="seconds")
        state["status"] = f"{name}_running"
        save_run_state(day, state)
        try:
            action(attempt)
            if name == "verification":
                validate_draft(draft, day, expected_window_id)
                OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
                os.replace(draft, md)
                mark_verification_complete(day, directory)
                print(f"Published {md}", flush=True)
            elif not artifact_exists():
                raise RuntimeError(f"{name} did not produce a valid persistent artifact")
            record_stage_success(day, state, name, datetime.now(TIMEZONE))
        except Exception as error:
            log = directory / f"{name}-attempt-{attempt}.log"
            message = error_with_log(error, log)
            record_stage_failure(day, state, name, datetime.now(TIMEZONE), message)
            print(
                f"{day} {name} failed; retry scheduled: {message}",
                file=sys.stderr,
                flush=True,
            )
            return "failed"

    validate_draft(md, day, read_json(packet, {}).get("window_id"))
    if no_send:
        return "ready"
    if email_delivery_complete(day):
        state["status"] = "email_complete"
        state["email_completed_at"] = now.isoformat(timespec="seconds")
        save_run_state(day, state)
        return "complete"

    email_stage = stage_state(state, "email")
    if not stage_is_due(email_stage, now):
        save_run_state(day, state)
        return "waiting"
    attempt = int(email_stage.get("attempts_total", 0)) + 1
    email_stage["attempts_total"] = attempt
    try:
        send_email(md)
        if not email_delivery_complete(day):
            raise RuntimeError("Email command finished but the delivery ledger is incomplete")
        record_stage_success(day, state, "email", datetime.now(TIMEZONE))
        state["status"] = "email_complete"
        state["email_completed_at"] = datetime.now(TIMEZONE).isoformat(timespec="seconds")
        save_run_state(day, state)
        return "complete"
    except Exception as error:
        record_stage_failure(day, state, "email", datetime.now(TIMEZONE), str(error))
        print(
            f"{day} email failed; retry scheduled: {error}",
            file=sys.stderr,
            flush=True,
        )
        return "failed"


def print_status(now: datetime) -> None:
    end = report_date(now)
    print(f"now={now.isoformat()} latest_report_date={end} state_root={STATE_ROOT}")
    for day in date_range(START_DATE, end):
        state = load_run_state(day)
        md = OUTPUT_ROOT / f"briefing_{day}.md"
        print(f"{day} status={state.get('status')} markdown={md.is_file()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="Print recovery state without running"
    )
    parser.add_argument(
        "--report-date", help="Manually process one explicit report date"
    )
    parser.add_argument(
        "--no-send", action="store_true", help="Generate Markdown without email"
    )
    args = parser.parse_args()
    now = datetime.now(TIMEZONE)
    if args.check:
        print_status(now)
        return 0

    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    with (LOG_ROOT / "schedule.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another briefing run is active; exiting.")
            return 0

        if args.report_date:
            days = [args.report_date]
        else:
            today = scheduled_report_date(now)
            if today is None:
                print("Today's 08:00 report cutoff has not closed; nothing to run.")
                return 0
            days = [today]
        exit_code = 0
        for day in days:
            result = process_day(day, datetime.now(TIMEZONE), no_send=args.no_send)
            print(f"{day}: {result}", flush=True)
            if result == "failed":
                # Keep resumable state, but automatic retries stop when the
                # local calendar date changes.
                exit_code = 1
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Preview or send a rendered briefing email."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from briefing_email import (  # noqa: E402
    delivery_key,
    load_env_file,
    load_recipients,
    read_delivery_state,
    render_email,
    send_smtp,
    smtp_settings_from_env,
    write_delivery_state,
)


DEFAULT_ENV = Path.home() / ".config" / "ai-daily-briefing" / "email.env"
DEFAULT_RECIPIENTS = ROOT / "email" / "recipients.txt"
DEFAULT_STATE = Path.home() / "Library" / "Logs" / "ai-daily-briefing" / "email-state.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render or send an AI briefing email")
    parser.add_argument("--markdown", required=True, help="Final briefing Markdown")
    parser.add_argument("--recipients", default=str(DEFAULT_RECIPIENTS))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--state-file", default=str(DEFAULT_STATE))
    parser.add_argument("--preview", help="Write the email HTML without sending")
    parser.add_argument("--send", action="store_true", help="Actually send email")
    parser.add_argument("--force", action="store_true", help="Ignore the delivery ledger")
    parser.add_argument(
        "--delivery-revision",
        default="",
        help="Optional revision ID with its own idempotent delivery ledger entries",
    )
    parser.add_argument(
        "--subject-prefix",
        default="",
        help="Optional prefix added to the rendered email subject",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    markdown_path = Path(args.markdown).expanduser().resolve()
    env_path = Path(args.env_file).expanduser()
    load_env_file(env_path)
    reply_to = os.environ.get("BRIEFING_EMAIL_REPLY_TO", "")
    briefing = render_email(markdown_path.read_text(encoding="utf-8"), reply_to=reply_to)
    if args.subject_prefix:
        briefing = replace(briefing, subject=args.subject_prefix + briefing.subject)

    if args.preview:
        preview_path = Path(args.preview).expanduser().resolve()
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(briefing.html, encoding="utf-8")
        print(f"Email preview: {preview_path}")

    if args.send and os.environ.get("BRIEFING_EMAIL_ENABLED", "0").lower() not in {"1", "true", "yes"}:
        print(f"Subject: {briefing.subject}")
        print("Email delivery is disabled; set BRIEFING_EMAIL_ENABLED=1 after testing.")
        return 0

    recipients_path = Path(args.recipients).expanduser().resolve()
    recipients = load_recipients(recipients_path)
    print(f"Subject: {briefing.subject}")
    print(f"Recipients: {len(recipients)}")
    if not args.send:
        print("Dry run only; pass --send to deliver.")
        return 0
    state_path = Path(args.state_file).expanduser().resolve()
    state = read_delivery_state(state_path)
    already_sent = set()
    if not args.force:
        already_sent = {
            recipient.lower()
            for recipient in recipients
            if delivery_key(
                briefing.report_date, recipient, args.delivery_revision
            ) in state
        }
    settings = smtp_settings_from_env()
    sent_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")

    def record_delivery(recipient: str) -> None:
        state[
            delivery_key(briefing.report_date, recipient, args.delivery_revision)
        ] = {
            "date": briefing.report_date,
            "recipient": recipient,
            "sent_at": sent_at,
            "revision": args.delivery_revision,
        }
        write_delivery_state(state_path, state)

    sent = send_smtp(
        briefing,
        recipients,
        settings,
        already_sent=already_sent,
        on_sent=record_delivery,
    )
    print(f"Delivered: {len(sent)}; skipped as already sent: {len(already_sent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

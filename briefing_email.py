#!/usr/bin/env python3
"""Render and send email-safe AI briefing messages."""

from __future__ import annotations

import hashlib
import json
import os
import re
import smtplib
import ssl
import subprocess
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from html import escape
from pathlib import Path
from typing import Callable, Iterable

import markdown as markdown_lib
from bs4 import BeautifulSoup, Tag


DATE_RE = re.compile(r"20\d{2}[-./]\d{1,2}[-./]\d{1,2}")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass(frozen=True)
class EmailBriefing:
    subject: str
    html: str
    text: str
    report_date: str
    item_count: int


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    security: str
    username: str
    password: str
    sender_name: str
    sender_email: str
    reply_to: str


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE pairs without overwriting an existing environment."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value[:1] == value[-1:] and value.startswith(("'", '"')):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def load_recipients(path: Path) -> list[str]:
    """Read one address per line, ignoring comments and duplicates."""
    recipients: list[str] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = raw_line.split("#", 1)[0].strip()
        if not value:
            continue
        _, address = parseaddr(value)
        normalized = address.lower()
        if not EMAIL_RE.fullmatch(normalized):
            raise ValueError(f"Invalid recipient at {path}:{line_number}: {value}")
        if normalized not in seen:
            recipients.append(address)
            seen.add(normalized)
    return recipients


def _plain_text(node: Tag) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def _split_item_detail(value: str) -> tuple[str, str, str]:
    metadata_match = re.search(r"(来源：.*?)(?=\s+入选理由：|$)", value)
    reason_match = re.search(r"(入选理由：.*)$", value)
    first_marker = min(
        [match.start() for match in (metadata_match, reason_match) if match is not None],
        default=len(value),
    )
    summary = value[:first_marker].strip()
    metadata = metadata_match.group(1).strip() if metadata_match else ""
    reason = reason_match.group(1).strip() if reason_match else ""
    return summary, metadata, reason


def _extract_report(markdown_text: str) -> tuple[str, str, list[dict[str, str]], list[str]]:
    normalized = re.sub(r"(?m)^ {3}(?=\S)", "    ", markdown_text)
    soup = BeautifulSoup(
        markdown_lib.markdown(normalized, extensions=["extra", "sane_lists"]),
        "html.parser",
    )
    heading = soup.find("h1")
    title = _plain_text(heading) if heading else "AI 工业界前沿简报"
    date_match = DATE_RE.search(title)
    report_date = date_match.group(0).replace(".", "-").replace("/", "-") if date_match else ""

    section = next(
        (
            node
            for node in soup.find_all("h2")
            if "本日十条行业信号" in _plain_text(node)
        ),
        None,
    )
    if section is None:
        raise ValueError("Markdown does not contain a '本日十条行业信号' section")
    items: list[dict[str, str]] = []
    for sibling in section.next_siblings:
        if isinstance(sibling, Tag) and sibling.name == "h2":
            break
        if not isinstance(sibling, Tag):
            continue
        if sibling.name == "ol":
            for item in sibling.find_all("li", recursive=False):
                link = item.find("a", href=True)
                if link is None:
                    continue
                title_text = _plain_text(link)
                item_text = _plain_text(item)
                detail = item_text[len(title_text) :].strip() if item_text.startswith(title_text) else item_text
                summary, metadata, reason = _split_item_detail(detail)
                items.append(
                    {
                        "title": title_text,
                        "url": str(link["href"]),
                        "summary": summary,
                        "metadata": metadata,
                        "reason": reason,
                    }
                )
        elif sibling.name == "p" and items:
            value = _plain_text(sibling)
            _, metadata, reason = _split_item_detail(value)
            if metadata:
                items[-1]["metadata"] = metadata
            if reason:
                items[-1]["reason"] = reason

    changes: list[str] = []
    changes_heading = next(
        (node for node in soup.find_all("h2") if _plain_text(node).startswith("相比")),
        None,
    )
    if changes_heading is not None:
        change_list = changes_heading.find_next_sibling(["ul", "ol"])
        if change_list is not None:
            changes = [_plain_text(item) for item in change_list.find_all("li", recursive=False)]
    return title, report_date, items, changes


def _item_html(number: int, item: dict[str, str]) -> str:
    metadata = ""
    if item["metadata"]:
        metadata = (
            '<p style="margin:12px 0 0;color:#687069;font-size:12px;line-height:1.65;">'
            f'{escape(item["metadata"])}</p>'
        )
    return f"""
      <tr>
        <td style="padding:0 22px 16px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                 style="border-collapse:separate;background:#ffffff;border:1px solid #dde2dc;border-radius:6px;">
            <tr>
              <td style="padding:17px 18px 18px;">
                <a href="{escape(item['url'], quote=True)}" style="color:#142019;text-decoration:none;font:700 17px/1.45 Arial,'PingFang SC','Microsoft YaHei',sans-serif;">{number}. {escape(item['title'])}</a>
                <p style="margin:9px 0 0;color:#28332c;font:14px/1.75 Arial,'PingFang SC','Microsoft YaHei',sans-serif;">{escape(item['summary'])}</p>
                {metadata}
              </td>
            </tr>
          </table>
        </td>
      </tr>"""


def render_email(markdown_text: str, *, reply_to: str = "") -> EmailBriefing:
    title, report_date, items, changes = _extract_report(markdown_text)
    if not items:
        raise ValueError("No briefing items found")
    subject_lead = items[0]["title"]
    if len(subject_lead) > 32:
        subject_lead = subject_lead[:31] + "…"
    subject = f"AI 工业界日报｜{report_date}｜{subject_lead} + {len(items) - 1} 条"
    preheader = f"今日 {len(items)} 条：{items[0]['title']}，以及模型、Agent、基础设施与产业应用动态。"

    changes_html = ""
    if changes:
        rows = "".join(
            '<tr><td valign="top" style="padding:4px 0;color:#2d6a4f;font-size:14px;">•</td>'
            f'<td style="padding:4px 0 4px 9px;color:#344139;font:13px/1.7 Arial,\'PingFang SC\',\'Microsoft YaHei\',sans-serif;">{escape(change)}</td></tr>'
            for change in changes[:3]
        )
        changes_html = f"""
      <tr><td style="padding:6px 22px 20px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eef3ee;border-radius:6px;padding:12px 15px;">
          <tr><td colspan="2" style="padding:0 0 6px;color:#17251c;font:700 13px Arial,'PingFang SC','Microsoft YaHei',sans-serif;">今日脉络</td></tr>
          {rows}
        </table>
      </td></tr>"""

    item_rows = "".join(_item_html(index, item) for index, item in enumerate(items, 1))
    unsubscribe = (
        f'如不再接收，请回复 <a href="mailto:{escape(reply_to, quote=True)}?subject=退订AI日报" style="color:#56675d;">退订</a>。'
        if reply_to
        else "如不再接收，请直接回复发件人退订。"
    )
    html = f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(subject)}</title></head>
<body style="margin:0;padding:0;background:#eef0ec;word-spacing:normal;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{escape(preheader)}</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;background:#eef0ec;">
    <tr><td align="center" style="padding:24px 8px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:680px;border-collapse:collapse;background:#f8f9f6;border:1px solid #d9ded8;">
        <tr><td style="padding:27px 24px 22px;background:#16211b;color:#ffffff;">
          <p style="margin:0 0 8px;color:#a9c6b4;font:700 11px Arial,sans-serif;text-transform:uppercase;">AI INDUSTRY BRIEFING</p>
          <h1 style="margin:0;font:700 26px/1.35 Arial,'PingFang SC','Microsoft YaHei',sans-serif;">AI 工业界前沿简报</h1>
          <p style="margin:8px 0 0;color:#d4ded7;font:14px/1.5 Arial,sans-serif;">{escape(report_date)} · {len(items)} 条关键信号 · 原文链接均可直接打开</p>
        </td></tr>
        {changes_html}
        {item_rows}
        <tr><td style="padding:8px 24px 26px;">
          <p style="margin:0;padding-top:17px;border-top:1px solid #d9ded8;color:#687069;font:12px/1.7 Arial,'PingFang SC','Microsoft YaHei',sans-serif;">
            本邮件由每日 AI 工业界简报自动生成。{unsubscribe}<br>
            邮件客户端若隐藏部分样式，所有标题和来源链接仍可正常访问。
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    text_lines = [title, "", preheader, ""]
    if changes:
        text_lines.extend(["今日脉络", *[f"- {change}" for change in changes[:3]], ""])
    for index, item in enumerate(items, 1):
        text_lines.extend(
            [
                f"{index}. {item['title']}",
                item["summary"],
                item["metadata"],
                item["url"],
                "",
            ]
        )
    text_lines.append("如不再接收，请直接回复发件人退订。")
    return EmailBriefing(subject, html, "\n".join(text_lines), report_date, len(items))


def smtp_settings_from_env() -> SmtpSettings:
    sender_value = os.environ.get("BRIEFING_EMAIL_FROM", "")
    sender_name, sender_email = parseaddr(sender_value)
    username = os.environ.get("BRIEFING_SMTP_USERNAME", "")
    password = os.environ.get("BRIEFING_SMTP_PASSWORD", "")
    keychain_service = os.environ.get("BRIEFING_SMTP_KEYCHAIN_SERVICE", "")
    if not password and keychain_service and username:
        try:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-w",
                    "-a",
                    username,
                    "-s",
                    keychain_service,
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            raise ValueError(
                f"Cannot read SMTP password from macOS Keychain service {keychain_service!r}"
            ) from error
        password = result.stdout.rstrip("\r\n")

    settings = SmtpSettings(
        host=os.environ.get("BRIEFING_SMTP_HOST", ""),
        port=int(os.environ.get("BRIEFING_SMTP_PORT", "465")),
        security=os.environ.get("BRIEFING_SMTP_SECURITY", "ssl").lower(),
        username=username,
        password=password,
        sender_name=sender_name or "AI 工业界简报",
        sender_email=sender_email,
        reply_to=os.environ.get("BRIEFING_EMAIL_REPLY_TO", ""),
    )
    missing = [
        name
        for name, value in {
            "BRIEFING_SMTP_HOST": settings.host,
            "BRIEFING_SMTP_USERNAME": settings.username,
            "BRIEFING_SMTP_PASSWORD": settings.password,
            "BRIEFING_EMAIL_FROM": settings.sender_email,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError("Missing email settings: " + ", ".join(missing))
    if settings.security not in {"ssl", "starttls", "plain"}:
        raise ValueError("BRIEFING_SMTP_SECURITY must be ssl, starttls, or plain")
    return settings


def _message(briefing: EmailBriefing, recipient: str, settings: SmtpSettings) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = briefing.subject
    message["From"] = formataddr((settings.sender_name, settings.sender_email))
    message["To"] = recipient
    if settings.reply_to:
        message["Reply-To"] = settings.reply_to
        message["List-Unsubscribe"] = f"<mailto:{settings.reply_to}?subject=退订AI日报>"
    message["Message-ID"] = make_msgid(domain=settings.sender_email.split("@")[-1])
    message.set_content(briefing.text)
    message.add_alternative(briefing.html, subtype="html")
    return message


def send_smtp(
    briefing: EmailBriefing,
    recipients: Iterable[str],
    settings: SmtpSettings,
    *,
    already_sent: set[str] | None = None,
    on_sent: Callable[[str], None] | None = None,
) -> list[str]:
    already_sent = already_sent or set()
    pending = [recipient for recipient in recipients if recipient.lower() not in already_sent]
    if not pending:
        return []
    context = ssl.create_default_context()
    if settings.security == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.host, settings.port, timeout=30, context=context
        )
    else:
        client = smtplib.SMTP(settings.host, settings.port, timeout=30)
    sent: list[str] = []
    try:
        client.ehlo()
        if settings.security == "starttls":
            client.starttls(context=context)
            client.ehlo()
        client.login(settings.username, settings.password)
        for recipient in pending:
            client.send_message(_message(briefing, recipient, settings))
            sent.append(recipient)
            if on_sent is not None:
                on_sent(recipient)
    finally:
        try:
            client.quit()
        except smtplib.SMTPException:
            client.close()
    return sent


def delivery_key(report_date: str, recipient: str) -> str:
    value = f"{report_date}\0{recipient.lower()}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def read_delivery_state(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def write_delivery_state(path: Path, state: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)

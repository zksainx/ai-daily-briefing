# AI Frontier Daily Briefing

[中文](README.md) | [English](README_EN.md)

A Chinese email digest of AI industry developments across domestic and international companies: models, multimodal and world models, embodied AI, agents, products, infrastructure, deployment, and commercial events. Pure academic research and Web3 are excluded.

## Architecture

```text
ai-daily-briefing/
├── ai_daily_briefing/        # Python application package
│   ├── __main__.py          # Collector CLI: python -m ai_daily_briefing
│   ├── collector.py         # Sources, normalization, dates, deduplication, candidate packets
│   ├── workflow.py          # Two-stage editing, verification, recovery, publication
│   ├── delivery.py          # Email preview and delivery CLI
│   ├── email.py             # Email rendering, SMTP, recipients, delivery ledger
│   ├── store.py             # SQLite history and source-health records
│   ├── retention.py         # 30-day repository report retention
│   └── html.py              # Optional standalone HTML reader
├── scripts/                 # Stable launch wrappers and skill installer
├── skills/daily-briefing/    # Editorial rules, collection helper, Markdown validator
├── tests/                   # Unit and command-entrypoint tests
├── email/                   # Configuration templates and local recipient list
├── outputs/                 # Final Markdown reports, excluded from Git
├── config.yaml              # Sources, collection caps, 80→30→10 limits, retention
├── requirements.txt
├── EMAIL_SETUP.md           # SMTP and email instructions, in Chinese
└── .github/workflows/       # CI checks
```

Data flow: sources → up to 80 raw candidates → up to 30 shortlisted candidates → verification and up to 10 final stories → Markdown → email bodies → individual delivery and ledger updates.

Business logic lives in the package. `scripts/scheduled_briefing.py` and `scripts/send_briefing_email.py` remain thin launch wrappers. The existing macOS LaunchAgent keeps its original script path.

## Setup and validation

Use Python 3.11+. The complete editorial workflow also requires an installed, authenticated Codex CLI. Sending email requires SMTP configuration.

Run from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# Offline sample: no network, saved files, or email
.venv/bin/python -m ai_daily_briefing --dry-run --no-save

# Compile and test
.venv/bin/python -m compileall -q ai_daily_briefing scripts
.venv/bin/python -m unittest discover -s tests
```

The old `python briefing.py` command has been replaced by `python -m ai_daily_briefing`. Collector output contains candidates, not the final edited briefing. Briefings remain in Chinese regardless of the documentation language.

## Usage

### Collect and generate

```bash
# Fetch raw candidates and print JSON; do not save or send
.venv/bin/python -m ai_daily_briefing --editorial-packet --no-save

# Read status without generating, sending, or deleting reports
.venv/bin/python -m ai_daily_briefing.workflow --check

# Generate or resume today's workflow, then email the current recipient list
.venv/bin/python -m ai_daily_briefing.workflow

# Generate or resume without email
.venv/bin/python -m ai_daily_briefing.workflow --no-send

# Remove expired report files only
.venv/bin/python -m ai_daily_briefing.workflow --cleanup-only
```

Use `--report-date YYYY-MM-DD` only for explicitly requested historical work. Completed runs are skipped; these commands do not force regeneration or redelivery.

Sources and collection limits are in [config.yaml](config.yaml). Codex is located through PATH; set `BRIEFING_CODEX` to override its executable path. Editorial calls use `gpt-6.1-sol` with `high` reasoning effort.

### Preview email

Replace the date with an existing report date:

```bash
.venv/bin/python -m ai_daily_briefing.delivery \
  --markdown outputs/briefing_YYYY-MM-DD.md \
  --preview /tmp/briefing-email.html
```

Previewing does not send mail. To configure SMTP:

1. Copy `email/email.env.example` to `~/.config/ai-daily-briefing/email.env` if no configuration exists, and set file permissions to `600`.
2. Fill in the sender, reply-to address, SMTP host, port, security mode, and username. Store the password in the macOS Keychain using the service named by `BRIEFING_SMTP_KEYCHAIN_SERVICE`, or configure the supported password environment variable.
3. Create `email/recipients.txt` with one address per line. Blank lines and `#` comments are supported; addresses are deduplicated.
4. Enable `BRIEFING_EMAIL_ENABLED=1`, then add `--send` to the delivery command when ready to send.

Messages are sent individually, so recipients do not see the other addresses. Successful deliveries are recorded immediately. Do not delete the ledger to resend; use `--force` only for an intentional resend, or `--delivery-revision` for a separate supplement. See [EMAIL_SETUP.md](EMAIL_SETUP.md) for detailed commands.

Install the local Codex skill with `./scripts/install-codex-skill.sh`, then invoke `$daily-briefing`. The helper uses a local checkout and never automatically clones the former upstream repository. A separately installed skill can locate this checkout through `DAILY_BRIEFING_PROJECT`.

## Daily policy and scheduling

- Start at 08:00 Asia/Shanghai. The report covers the previous day's 08:00 inclusive through the report day's 08:00 exclusive. Its date is the closing date.
- Collect up to 80 candidates, shortlist up to 30, and verify up to 10 final stories. Collection does not use keyword relevance scores or category quotas.
- Previously sent events are excluded unless there is a new version, availability, benchmark, or material development. Publish fewer stories when evidence is insufficient.
- Each story has a linked title, a 2–3 sentence overview, and a 2–3 sentence technical summary. The subject is `AI前沿日报｜YYYY-MM-DD`.
- Save only `outputs/briefing_YYYY-MM-DD.md`. Render HTML and plain-text email bodies in memory.
- Preserve stage progress. Failed stages use 10-, 30-, and 60-minute retry delays, checked by the hourly scheduler. Automatic recovery only handles the current date; it never backfills older days.
- The delivery ledger tracks the report date, recipient, and optional revision. Retries skip recipients already sent that delivery.

The existing macOS LaunchAgent is `~/Library/LaunchAgents/com.kxzhang.ai-briefing-email-daily.plist`. It starts at 08:00 and checks every 3600 seconds. This is local machine configuration and must be installed separately on a new machine. Delivery follows completion of editing; sleep or network outages may delay it.

```bash
launchctl print gui/$(id -u)/com.kxzhang.ai-briefing-email-daily
tail -n 80 ~/Library/Logs/ai-daily-briefing/email-daily.log
tail -n 80 ~/Library/Logs/ai-daily-briefing/email-daily-error.log
```

## Files and retention

| Location | Purpose and retention |
| --- | --- |
| Dated reports in `outputs/` and the repository root | Keep the latest 30 calendar days, including today; permanently delete older files |
| `~/Library/Application Support/ai-daily-briefing/runs/YYYY-MM-DD/` | Keep candidates, shortlist, verification progress, drafts, and stage state |
| `~/Library/Logs/ai-daily-briefing/` | Keep logs and the `email-state.json` delivery ledger |
| `email/recipients.txt` | Local recipient list, excluded from Git |
| `~/.config/ai-daily-briefing/email.env` | Local SMTP configuration, excluded from Git; passwords may use Keychain |

Set `output.retention_days` to change the default of 30. Age comes from the report date in the filename, not its modification time. Cleanup runs whenever the scheduled workflow starts or the collector saves files. It only matches valid dated `briefing_`, `candidates_`, `editorial_packet_`, and `weekly_review_` files with MD, HTML, TXT, or JSON extensions. It does not recurse, follow symlinks, or clean directories outside the repository.

Editorial instructions live in the [daily briefing skill](skills/daily-briefing/SKILL.md), and maintenance requirements in [AGENTS.md](AGENTS.md). Project repository: [zksainx/ai-daily-briefing](https://github.com/zksainx/ai-daily-briefing). Local briefings, candidate packets, and weekly reports are all excluded from Git.

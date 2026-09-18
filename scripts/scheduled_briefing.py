"""Generate and email the previous day's AI industry briefing."""
import argparse
from datetime import datetime, timedelta
import fcntl
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CODEX = '/Users/kxzhang/.nvm/versions/node/v22.17.1/bin/codex'
sys.path.insert(0, str(ROOT))


def report_date(now):
    day = now.astimezone(ZoneInfo('Asia/Shanghai')).date() - timedelta(days=1)
    return day.isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        now = datetime.now(ZoneInfo('Asia/Shanghai'))
        print(now.isoformat(), report_date(now))
        return
    day = report_date(datetime.now(ZoneInfo('Asia/Shanghai')))
    state = Path('/Users/kxzhang/Library/Logs/ai-daily-briefing')
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'schedule.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        output = ROOT / 'outputs'
        output.mkdir(exist_ok=True)
        md = output / f'briefing_{day}.md'
        if not md.exists():
            from briefing import DailyBriefing
            with tempfile.TemporaryDirectory(prefix='ai-briefing-') as scratch:
                scratch = Path(scratch)
                briefing = DailyBriefing(config_path=str(ROOT / 'config.yaml'), history_enabled=False)
                data = briefing.generate_data()
                if not data['sections']['editorial_queue']:
                    raise RuntimeError('No candidates; refusing to publish an empty report')
                packet = scratch / 'candidates.json'
                packet.write_text(briefing.format_output(data, 'json'), encoding='utf-8')
                draft = scratch / md.name
                prompt = f'''Read skills/daily-briefing/SKILL.md and complete the fixed-pool editorial workflow.
Report date: {day}, Asia/Shanghai, ending at the following midnight. The already collected candidate packet is {packet}.
Read all up to 80 candidates and their raw summaries. Independently select the ten most important AI INDUSTRY stories, Chinese and international, including models, multimodal, embodied AI, products, agents, infrastructure and commercialization. SemiAnalysis is an important industry-analysis source. No keyword scoring or automatic ranking. No academic-paper coverage. Do not collect another pool.
Open original sources for shortlisted stories, verify facts and actual publication dates (not sitemap modification dates); exclude anything published after the report cutoff. Prioritize the report day; if recent supplemental stories are necessary, explicitly label their dates. Never fabricate ten stories if evidence is insufficient.
Write the final Chinese Top 10 to {draft}. Each linked item should contain only a concrete three- or four-sentence Chinese news summary followed by source/date/confidence metadata. Do not write an "入选理由" or "为什么重要" paragraph in the final briefing: candidate inclusion/exclusion reasoning belongs only in your private scratch reasoning. Each sentence should add distinct information; use fewer sentences when the source lacks detail, without padding or inventing facts. For technical stories, add three or four factual sentences describing the architecture, interface, deployment method, implementation change, or benchmark setup when the source supports it. Do not append rebuttal-style sentences such as "这不代表……", "不能据此认为……", "仍需……", or generic caveats; state the supported facts directly and preserve source attribution in the metadata. All final items must come from the supplied candidate pool. Keep any reasoning log only in {scratch}; do not produce a selection file or candidate files in outputs.
Run .venv/bin/python skills/daily-briefing/scripts/validate-briefing.py on your draft. Finish the editorial pass in this run, not just a plan or collection status. This is an email-only workflow: produce only the Markdown draft, without a standalone HTML file. The runner will publish the Markdown and send email generated directly from it. Do not modify code, config, skills, existing reports or any other files. No commits or messages to external services.'''
                subprocess.run([CODEX, 'exec', '-C', str(ROOT), '--model', 'gpt-5.6-sol',
                                '-c', 'model_reasoning_effort="high"',
                                '--sandbox', 'workspace-write',
                                '-c', 'sandbox_workspace_write.network_access=true',
                                '-c', 'web_search="live"', '--ephemeral', '--color', 'never',
                                '--add-dir', str(scratch), prompt], check=True, timeout=5400)
                text = draft.read_text(encoding='utf-8')
                count = len(re.findall(r'^\d+\. \[', text, re.MULTILINE))
                if not 1 <= count <= 10:
                    raise RuntimeError(f'Expected 1-10 editorial items, got {count}')
                subprocess.run([sys.executable, str(ROOT / 'skills/daily-briefing/scripts/validate-briefing.py'), str(draft)], check=True)
                os.replace(draft, md)
                print(f'Published {md}', flush=True)

        subprocess.run([
            sys.executable,
            str(ROOT / 'scripts/send_briefing_email.py'),
            '--markdown', str(md),
            '--recipients', str(ROOT / 'email/recipients.txt'),
            '--send',
        ], check=True)


if __name__ == '__main__':
    main()

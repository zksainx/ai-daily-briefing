# 邮件推送方案

日报邮件直接把 Top 10 写入正文，收件人无需下载附件。邮件使用内联样式、表格布局和纯文本备用正文，兼容常见网页邮箱、Outlook 和手机邮件客户端；不包含 JavaScript。

## 工作流

1. 定时任务永久保存最多 80 条原始候选；第一阶段只选 30 条短名单，第二阶段核验短名单并生成最多 10 条的 `briefing_YYYY-MM-DD.md`。
2. 候选包、短名单、核验进度和草稿保存在本机状态目录以便断点恢复；Markdown 仍是唯一对外发布的日报内容文件。邮件 HTML 和纯文本正文在内存中生成，不保存独立网页 HTML。
3. 报告文件发布成功后，向收件人逐封发送，地址不会相互暴露。
4. 每个“报告日期 + 收件地址”成功后立即写入本地发送账本；任务重试只补发尚未成功的地址。
5. 采集、选 30、核验写稿和邮件阶段各自保存进度；失败后按 10、30、60 分钟补跑，邮件重试复用 MD，无需重新采集和选稿。

## 收件人

真实名单保存在被 Git 忽略的 `email/recipients.txt`，每行一个地址，可使用 `#` 写注释：

```text
member1@example.com
member2@example.com
```

新增组员只需追加一行。发送时每人收到独立邮件，不使用公开抄送。

## 发件配置

建议使用专门的发件邮箱和 SMTP 应用密码。交大邮箱官方 SMTP 配置为 `mail.sjtu.edu.cn:465`，使用 SSL。将非敏感配置保存到：

```text
~/.config/ai-daily-briefing/email.env
```

参考 `email/email.env.example`，然后限制文件权限：

```bash
chmod 600 ~/.config/ai-daily-briefing/email.env
```

在 macOS 上把密码写入 Keychain，命令会在终端中安全提示输入，不要把密码发到聊天中：

```bash
security add-generic-password -U \
  -a "你的SMTP用户名" \
  -s "ai-daily-briefing-smtp" \
  -w
```

程序通过 `BRIEFING_SMTP_KEYCHAIN_SERVICE` 读取该密码。密码和 API Token 不写入仓库、`config.yaml` 或 LaunchAgent plist。若未来使用自有域名群发，应同时配置 SPF、DKIM 和 DMARC。

## 预览和测试

仅生成预览，不发送：

```bash
.venv/bin/python scripts/send_briefing_email.py \
  --markdown outputs/briefing_2026-09-17.md \
  --preview /tmp/briefing-email.html
```

检查预览后，在环境文件中设置 `BRIEFING_EMAIL_ENABLED=1`，发送到当前测试名单：

```bash
.venv/bin/python scripts/send_briefing_email.py \
  --markdown outputs/briefing_2026-09-17.md \
  --send
```

同一天重复运行默认不会重发。只有人工确认需要重复测试时才添加 `--force`。

## 定时发送

日报编辑通过 `codex exec --model gpt-5.6-terra -c 'model_reasoning_effort="xhigh"'` 固定模型和推理强度，不随全局默认模型变化。

`scripts/scheduled_briefing.py` 已在日报发布后调用邮件发送器。启动时会从 2026-09-18 起检查缺失日期，并优先补做最早的未完成日报。运行状态位于 `~/Library/Application Support/ai-daily-briefing/runs/YYYY-MM-DD/`，候选包不会再放入临时目录。

LaunchAgent `com.kxzhang.ai-briefing-email-daily` 每天北京时间 00:00 运行，并每 1 小时执行一次轻量恢复检查。没有缺失任务时检查会立即退出；发生失败时会在状态文件允许重试后的下一次小时检查中补跑。它长期生效，没有结束日期。

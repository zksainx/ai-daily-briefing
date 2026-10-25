# 邮件配置

日报从最终 Markdown 生成 HTML 邮件正文和纯文本备用正文，不产生独立网页文件。主题为 `AI前沿日报｜YYYY-MM-DD`；条目数字放在标题内，每条分别包含「概述」和「技术总结」，各 2–3 句。

定时和文件保留规则见 [README.md](README.md)。

## 收件人

实际名单是 `email/recipients.txt`，每行一个地址，支持空行和 `#` 注释。发送前去重，每人收到独立邮件，其他地址不公开。文件已被 Git 忽略。

```text
member1@example.com
member2@example.com
```

## 发件配置

将 SMTP 配置放在 `~/.config/ai-daily-briefing/email.env`，参考 [配置模板](email/email.env.example)：

```bash
mkdir -p ~/.config/ai-daily-briefing
cp email/email.env.example ~/.config/ai-daily-briefing/email.env
chmod 600 ~/.config/ai-daily-briefing/email.env
```

已有配置无需再次复制。填写 `BRIEFING_EMAIL_FROM`、`BRIEFING_EMAIL_REPLY_TO`、`BRIEFING_SMTP_HOST`、端口、安全协议、SMTP 用户名。交大邮箱当前配置为 `mail.sjtu.edu.cn:465`、`ssl`；SMTP 用户名使用发件邮箱完整地址。

macOS 密码放在钥匙串，账户名须与 SMTP 用户名一致。下面命令会提示输入密码：

```bash
security add-generic-password -U \
  -a "你的发件邮箱完整地址" \
  -s "ai-daily-briefing-smtp" \
  -w
```

环境文件中保留 `BRIEFING_SMTP_KEYCHAIN_SERVICE=ai-daily-briefing-smtp`，确认配置后设置 `BRIEFING_EMAIL_ENABLED=1`。不要把密码或 Token 写进仓库或 plist。

## 预览与手动发送

将下面的 `YYYY-MM-DD` 替换为已有报告日期：

```bash
# 仅预览，不发送；这个临时 HTML 可自行删除
.venv/bin/python scripts/send_briefing_email.py \
  --markdown outputs/briefing_YYYY-MM-DD.md \
  --preview /tmp/briefing-email.html

# 向当前收件人名单发送
.venv/bin/python scripts/send_briefing_email.py \
  --markdown outputs/briefing_YYYY-MM-DD.md --send
```

成功发送后立即记入 `~/Library/Logs/ai-daily-briefing/email-state.json`，同日已成功的地址默认跳过。只有明确要重发时才使用 `--force`；发送补充稿时可用 `--delivery-revision` 建立独立发送记录。不要删除发送账本来重发邮件。

邮件里的退订入口是回复邮件请求移除名单，需要维护者从 `email/recipients.txt` 删除对应地址；没有网站自动退订服务。

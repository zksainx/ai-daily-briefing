import tempfile
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from ai_daily_briefing.email import (
    SmtpSettings,
    delivery_key,
    load_recipients,
    render_email,
    send_smtp,
)


SAMPLE = """# AI 工业界前沿简报 · 2026-09-17

## 本日十条行业信号

1. [公司发布模型](https://example.com/model)
   概述：公司发布实时多模态模型，支持音频和图像输入。模型已经向企业 API 用户开放。

   技术总结：模型通过统一接口处理文本、图像和音频。流式接口支持工具调用和增量输出。

   来源：公司官网 · 官方确认 · 中游

2. [芯片进入部署](https://example.com/chip)
   概述：供应商计划向数据中心交付最多 100 套推理设备。首批系统将在本季度上线。

   技术总结：设备使用低精度推理和统一内存。机架通过高速互连接入现有集群。

   来源：行业媒体 · 单源信号 · 上游

## 相比上一期的新变化

- 模型能力从文本扩展到实时音视频。
- 基础设施开始进入区域部署。
"""


class BriefingEmailTests(unittest.TestCase):
    def test_renders_email_safe_digest(self):
        email = render_email(SAMPLE, reply_to="owner@example.com")

        self.assertEqual(email.report_date, "2026-09-17")
        self.assertEqual(email.item_count, 2)
        self.assertEqual(email.subject, "AI前沿日报｜2026-09-17")
        self.assertIn("公司发布实时多模态模型", email.html)
        self.assertIn("技术总结：", email.html)
        self.assertIn("流式接口支持工具调用", email.html)
        self.assertIn("概述：公司发布实时多模态模型", email.text)
        self.assertIn("技术总结：模型通过统一接口", email.text)
        self.assertIn("今日脉络", email.html)
        self.assertNotIn("为什么重要", email.html)
        self.assertNotIn("入选理由", email.html)
        self.assertNotIn("<script", email.html.lower())
        self.assertNotIn("公司发布模型 公司发布模型", email.html)
        self.assertIn("https://example.com/model", email.text)

    def test_load_recipients_ignores_comments_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "recipients.txt"
            path.write_text(
                "# team\nOne@example.com\none@example.com\nTwo <two@example.com>\n",
                encoding="utf-8",
            )
            self.assertEqual(load_recipients(path), ["One@example.com", "two@example.com"])

    def test_load_recipients_rejects_invalid_address(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "recipients.txt"
            path.write_text("not-an-email\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_recipients(path)

    def test_delivery_key_is_date_and_recipient_specific(self):
        first = delivery_key("2026-09-17", "One@example.com")
        self.assertEqual(first, delivery_key("2026-09-17", "one@example.com"))
        self.assertNotEqual(first, delivery_key("2026-09-18", "one@example.com"))
        self.assertNotEqual(
            first,
            delivery_key("2026-09-17", "one@example.com", "summary-tech-v2"),
        )

    @patch("ai_daily_briefing.email.smtplib.SMTP_SSL")
    def test_smtp_sends_individual_messages_and_reports_each_success(self, smtp_ssl):
        client = MagicMock()
        smtp_ssl.return_value = client
        settings = SmtpSettings(
            host="smtp.example.com",
            port=465,
            security="ssl",
            username="sender@example.com",
            password="secret",
            sender_name="AI 简报",
            sender_email="sender@example.com",
            reply_to="sender@example.com",
        )
        delivered = []

        sent = send_smtp(
            render_email(SAMPLE),
            ["one@example.com", "two@example.com"],
            settings,
            on_sent=delivered.append,
        )

        self.assertEqual(sent, ["one@example.com", "two@example.com"])
        self.assertEqual(delivered, sent)
        self.assertEqual(client.send_message.call_count, 2)
        messages = [call.args[0] for call in client.send_message.call_args_list]
        self.assertEqual([message["To"] for message in messages], sent)
        self.assertNotIn("two@example.com", str(messages[0]))


if __name__ == "__main__":
    unittest.main()

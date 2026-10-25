import unittest
from unittest.mock import patch

from ai_daily_briefing.collector import DailyBriefing


class RawCandidateTests(unittest.TestCase):
    def setUp(self):
        self.briefing = DailyBriefing(history_enabled=False)
        self.briefing.config.setdefault("editorial", {})["raw_candidates"] = True

    def test_non_keyword_article_survives_fetch_and_editorial_filter(self):
        source = {"name": "SemiAnalysis", "url": "https://example.com/feed"}
        feed = b"<rss><channel><item><title>Behind the meter</title><link>https://example.com/power</link><description>Electricity supply constraints.</description></item></channel></rss>"
        with patch.object(self.briefing, "_get_content", return_value=feed):
            rows = self.briefing._fetch_industry_feed(source, 4)
        self.assertEqual(len(rows), 1)
        rows[0]["event_types"] = ["research"]
        self.assertTrue(self.briefing._keep_industry_item(rows[0], "ai"))
        queue = self.briefing.generate_editorial_queue(rows)
        self.assertEqual(queue[0]["raw_summary"], "Electricity supply constraints.")
        self.assertNotIn("score", queue[0])

    def test_queue_uses_source_rotation_and_dates_instead_of_scores(self):
        self.briefing.config["pipeline"]["candidate_pool_max"] = 2
        rows = [
            {"title": "Old", "source": "A", "published_at": "2026-09-11", "overall_score": 100},
            {"title": "New", "source": "A", "published_at": "2026-09-13", "overall_score": 1},
            {"title": "Other", "source": "B", "overall_score": 0},
        ]
        self.assertEqual([row["title"] for row in self.briefing.generate_editorial_queue(rows)], ["New", "Other"])

    def test_semantic_request_is_deferred_but_dates_are_checked(self):
        self.briefing.briefing_mode = "industry"
        self.assertTrue(self.briefing._matches_request({"title": "Electricity supply"}))
        self.briefing.lookback_hours = 24
        self.assertFalse(self.briefing._matches_request({"title": "Electricity supply", "published_at": "2000-01-01T00:00:00Z"}))

    def test_default_collection_window_is_48_hours(self):
        self.assertEqual(self.briefing.config["quality"]["max_feed_age_days"], 2)
        self.assertEqual(
            self.briefing.config["quality"]["model_release_max_age_days"], 2
        )
        self.assertEqual(
            self.briefing.config["sources"]["hacker_news"]["lookback_hours"], 48
        )

import datetime as dt
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from intelligence_engine import (
    extract_items,
    fingerprint,
    normalized_signal,
    score_signal,
)

POLICY = {
    "minimum_evidence_score": 3,
    "minimum_total_score": 18,
    "max_signal_age_days": 30,
    "max_items_per_source": 12,
    "max_issues_per_run": 5,
    "request_timeout_seconds": 12,
    "max_response_bytes": 2000000,
    "max_title_chars": 180,
    "max_summary_chars": 1200,
}
SOURCE = {
    "id": "fixture-source",
    "type": "json",
    "platform": "sentinel-apex",
    "purpose": "threat-intelligence",
    "url": "https://intel.cyberdudebivash.com/api/feed.json",
    "trust_level": 4,
    "enabled": True,
}
PLATFORMS = {
    "sentinel-apex": {
        "id": "sentinel-apex",
        "name": "CYBERDUDEBIVASH® Sentinel APEX",
    }
}
NOW = dt.datetime(2026, 8, 17, 10, 0, tzinfo=dt.timezone.utc)


class CampaignIntelligenceTests(unittest.TestCase):
    def test_extracts_nested_items(self):
        payload = {"data": {"results": [{"title": "Signal A"}, {"title": "Signal B"}]}}
        items = extract_items(payload, 10)
        self.assertEqual([item["title"] for item in items], ["Signal A", "Signal B"])

    def test_high_evidence_current_signal_is_eligible(self):
        raw = {
            "id": "CVE-2026-9999",
            "title": "Critical actively exploited CVE-2026-9999 affects enterprise platform",
            "summary": "Threat intelligence report with API detection guidance and enterprise mitigation.",
            "url": "https://intel.cyberdudebivash.com/reports/example",
            "published_at": "2026-08-17T08:00:00Z",
        }
        signal = normalized_signal(SOURCE, raw, POLICY)
        self.assertIsNotNone(signal)
        scored = score_signal(signal, PLATFORMS, POLICY, now=NOW)
        self.assertTrue(scored["eligible"])
        self.assertGreaterEqual(scored["scores"]["evidence_strength"], 3)
        self.assertGreaterEqual(scored["total_score"], 18)

    def test_low_trust_signal_fails_evidence_gate(self):
        source = {**SOURCE, "trust_level": 2}
        raw = {
            "title": "Critical release launch",
            "summary": "Enterprise AI security platform release.",
            "published_at": "2026-08-17T08:00:00Z",
        }
        signal = normalized_signal(source, raw, POLICY)
        scored = score_signal(signal, PLATFORMS, POLICY, now=NOW)
        self.assertFalse(scored["eligible"])
        self.assertEqual(scored["scores"]["evidence_strength"], 2)

    def test_stale_signal_is_not_eligible(self):
        raw = {
            "title": "Critical vulnerability report",
            "summary": "Enterprise threat intelligence analysis.",
            "published_at": "2026-06-01T00:00:00Z",
        }
        signal = normalized_signal(SOURCE, raw, POLICY)
        scored = score_signal(signal, PLATFORMS, POLICY, now=NOW)
        self.assertFalse(scored["eligible"])
        self.assertEqual(scored["scores"]["timeliness"], 0)

    def test_fingerprint_is_deterministic(self):
        signal = {
            "source_id": "fixture-source",
            "external_id": "signal-123",
            "title": "Title",
            "url": "https://example.com",
            "published_at": "2026-08-17T08:00:00+00:00",
        }
        first = fingerprint(signal)
        second = fingerprint(dict(signal))
        self.assertEqual(first, second)
        self.assertEqual(len(first), 20)


if __name__ == "__main__":
    unittest.main()

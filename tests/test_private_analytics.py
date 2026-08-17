import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from private_analytics import (
    AnalyticsValidationError,
    aggregate_records,
    enforce_private_runtime_path,
    validate_record,
)

POLICY = {
    "runtime_boundary": "private-only",
    "public_repository_runtime_inputs_forbidden": True,
    "retention_days": 90,
    "max_batch_records": 5000,
    "providers": [
        {"id": "manual-aggregate", "enabled": True, "mode": "file"},
        {"id": "ga4-data-api", "enabled": False, "mode": "api"},
    ],
    "record_types": {
        "funnel": {"required_metrics": ["sessions","engaged_sessions","cta_events","leads","conversions"]},
        "assist": {"required_metrics": ["journeys","assisted_conversions"]},
    },
    "allowed_acquisition_channels": ["linkedin","organic-search","direct"],
    "privacy": {
        "aggregate_only": True,
        "forbidden_fields": ["email","ip_address","user_id","session_id"],
        "forbidden_key_substrings": ["token","secret","authorization","credential"],
        "max_landing_path_chars": 200,
    },
}
ECOSYSTEM = {
    "platforms": [
        {"id": "official-portal", "url": "https://www.cyberdudebivash.com/"},
        {"id": "ai-security-hub", "url": "https://cyberdudebivash.in/"},
    ]
}


def funnel():
    return {
        "schema_version": 1,
        "data_classification": "private-aggregate",
        "provider": "manual-aggregate",
        "record_type": "funnel",
        "property_host": "www.cyberdudebivash.com",
        "platform": "official-portal",
        "window_start": "2026-08-01",
        "window_end": "2026-08-07",
        "campaign_id": "cdb-20260801-authority-all-12345678",
        "channel": "linkedin",
        "landing_path": "/",
        "metrics": {
            "sessions": 100,
            "engaged_sessions": 70,
            "cta_events": 20,
            "leads": 5,
            "conversions": 2,
        },
    }


def assist():
    return {
        "schema_version": 1,
        "data_classification": "private-aggregate",
        "provider": "manual-aggregate",
        "record_type": "assist",
        "window_start": "2026-08-01",
        "window_end": "2026-08-07",
        "campaign_id": "cdb-20260801-authority-all-12345678",
        "from_platform": "official-portal",
        "to_platform": "ai-security-hub",
        "metrics": {"journeys": 25, "assisted_conversions": 3},
    }


class PrivateAnalyticsTests(unittest.TestCase):
    def test_valid_funnel_record(self):
        validate_record(funnel(), POLICY, ECOSYSTEM)

    def test_person_level_field_rejected(self):
        record = funnel()
        record["email"] = "person@example.com"
        with self.assertRaises(AnalyticsValidationError):
            validate_record(record, POLICY, ECOSYSTEM)

    def test_platform_host_mismatch_rejected(self):
        record = funnel()
        record["property_host"] = "cyberdudebivash.in"
        with self.assertRaises(AnalyticsValidationError):
            validate_record(record, POLICY, ECOSYSTEM)

    def test_query_data_in_landing_path_rejected(self):
        record = funnel()
        record["landing_path"] = "/pricing?email=a@example.com"
        with self.assertRaises(AnalyticsValidationError):
            validate_record(record, POLICY, ECOSYSTEM)

    def test_impossible_funnel_relationship_rejected(self):
        record = funnel()
        record["metrics"]["conversions"] = 10
        with self.assertRaises(AnalyticsValidationError):
            validate_record(record, POLICY, ECOSYSTEM)

    def test_disabled_provider_rejected(self):
        record = funnel()
        record["provider"] = "ga4-data-api"
        with self.assertRaises(AnalyticsValidationError):
            validate_record(record, POLICY, ECOSYSTEM)

    def test_same_platform_assist_rejected(self):
        record = assist()
        record["to_platform"] = "official-portal"
        with self.assertRaises(AnalyticsValidationError):
            validate_record(record, POLICY, ECOSYSTEM)

    def test_aggregate_scorecard_contains_assist_edges(self):
        scorecard = aggregate_records([funnel(), assist()], POLICY, ECOSYSTEM)
        self.assertEqual(scorecard["metrics"]["sessions"], 100)
        self.assertEqual(
            scorecard["assist_edges"]["official-portal->ai-security-hub"]["assisted_conversions"],
            3,
        )
        self.assertEqual(scorecard["data_classification"], "private-aggregate-derived")

    def test_repo_runtime_path_outside_private_is_rejected(self):
        with self.assertRaises(AnalyticsValidationError):
            enforce_private_runtime_path(ROOT / "reports" / "analytics.json")


if __name__ == "__main__":
    unittest.main()

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seo_opportunity import (
    SeoValidationError,
    build_report,
    score_topic,
    validate_registry,
    validate_topic,
)

POLICY = {
    "score_version": "seo-opportunity-v1",
    "allowed_intents": ["informational","commercial","transactional","navigational"],
    "allowed_external_evidence_status": ["none","verified"],
    "approved_external_providers": ["google-search-console"],
    "internal_weights": {
        "strategic_fit": 0.25,
        "commercial_intent": 0.20,
        "authority_fit": 0.20,
        "landing_readiness": 0.15,
        "content_gap": 0.20,
    },
    "external_weights": {"demand_score": 0.60, "competition_opportunity": 0.40},
    "blend": {"internal": 0.75, "external": 0.25},
    "confidence_multiplier": {"internal-only": 0.85, "verified-external": 1.0},
    "recommendation_threshold": 65.0,
    "max_report_items": 20,
    "rules": {
        "numeric_signals_min": 0,
        "numeric_signals_max": 5,
        "ranking_claims_require_verified_external_evidence": True,
        "search_volume_claims_forbidden_without_source": True,
    },
}
ECOSYSTEM = {
    "platforms": [
        {"id": "official-portal", "url": "https://www.cyberdudebivash.com/"},
        {"id": "ai-security-hub", "url": "https://cyberdudebivash.in/"},
        {"id": "academy", "url": "https://academy.cyberdudebivash.com/"},
    ]
}


def topic():
    return {
        "schema_version": 1,
        "topic_id": "ai-security-assessment",
        "cluster": "AI Security",
        "query": "ai security assessment",
        "intent": "commercial",
        "target_platform": "ai-security-hub",
        "landing_path": "/",
        "source_platforms": ["official-portal", "academy"],
        "internal_signals": {
            "strategic_fit": 5,
            "commercial_intent": 5,
            "authority_fit": 5,
            "landing_readiness": 5,
            "content_gap": 4,
        },
        "external_evidence": {"status": "none"},
    }


class SeoOpportunityTests(unittest.TestCase):
    def test_internal_only_topic_is_scored_without_market_claim(self):
        scored = score_topic(topic(), POLICY)
        self.assertEqual(scored["confidence"], "internal-only")
        self.assertFalse(scored["ranking_claim_allowed"])
        self.assertIsNone(scored["external_score"])
        self.assertGreater(scored["decision_score"], 0)

    def test_verified_external_evidence_changes_confidence(self):
        item = topic()
        item["external_evidence"] = {
            "status": "verified",
            "provider": "google-search-console",
            "as_of": "2026-08-16",
            "demand_score": 5,
            "competition_opportunity": 4,
        }
        validate_topic(item, POLICY, ECOSYSTEM)
        scored = score_topic(item, POLICY)
        self.assertEqual(scored["confidence"], "verified-external")
        self.assertTrue(scored["ranking_claim_allowed"])
        self.assertIsNotNone(scored["external_score"])

    def test_unverified_evidence_cannot_carry_metrics(self):
        item = topic()
        item["external_evidence"] = {"status": "none", "demand_score": 5}
        with self.assertRaises(SeoValidationError):
            validate_topic(item, POLICY, ECOSYSTEM)

    def test_unknown_platform_rejected(self):
        item = topic()
        item["target_platform"] = "unknown"
        with self.assertRaises(SeoValidationError):
            validate_topic(item, POLICY, ECOSYSTEM)

    def test_query_parameter_in_landing_path_rejected(self):
        item = topic()
        item["landing_path"] = "/?campaign=x"
        with self.assertRaises(SeoValidationError):
            validate_topic(item, POLICY, ECOSYSTEM)

    def test_duplicate_query_rejected(self):
        one = topic()
        two = copy.deepcopy(one)
        two["topic_id"] = "second-topic"
        registry = {"schema_version": 1, "topics": [one, two]}
        with self.assertRaises(SeoValidationError):
            validate_registry(registry, POLICY, ECOSYSTEM)

    def test_report_orders_and_recommends(self):
        one = topic()
        two = copy.deepcopy(one)
        two["topic_id"] = "ai-security-training"
        two["query"] = "ai security training"
        two["target_platform"] = "academy"
        two["source_platforms"] = ["official-portal", "ai-security-hub"]
        two["internal_signals"] = {
            "strategic_fit": 3,
            "commercial_intent": 3,
            "authority_fit": 4,
            "landing_readiness": 4,
            "content_gap": 3,
        }
        report = build_report({"schema_version": 1, "topics": [two, one]}, POLICY, ECOSYSTEM)
        self.assertEqual(report["opportunities"][0]["topic_id"], "ai-security-assessment")
        self.assertGreaterEqual(report["recommended_count"], 1)


if __name__ == "__main__":
    unittest.main()

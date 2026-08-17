import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from growth_attribution import (
    GrowthValidationError,
    aggregate_records,
    build_tracked_url,
    campaign_id,
    create_campaign_bundle,
    transition_campaign,
    validate_performance_record,
)


POLICY = {
    "campaign_id_prefix": "cdb",
    "allowed_states": ["planned","approved","active","measuring","completed","rejected","archived"],
    "state_transitions": {
        "planned": ["approved","rejected"],
        "approved": ["active","rejected"],
        "active": ["measuring","completed"],
        "measuring": ["completed"],
        "completed": ["archived"],
        "rejected": ["archived"],
        "archived": []
    },
    "utm": {
        "required_parameters": ["utm_source","utm_medium","utm_campaign"],
        "optional_parameters": ["utm_content","utm_term"],
        "max_value_chars": 120
    },
    "performance": {
        "required_metrics": ["impressions","clicks","engaged_visits","cta_actions","leads","conversions"],
        "minimum_clicks_for_channel_recommendation": 25,
        "targets_pct": {
            "ctr": 2.0,
            "engaged_visit_rate": 60.0,
            "cta_rate": 5.0,
            "lead_rate": 1.0,
            "conversion_rate": 0.5
        },
        "score_weights": {
            "ctr": 0.20,
            "engaged_visit_rate": 0.20,
            "cta_rate": 0.25,
            "lead_rate": 0.20,
            "conversion_rate": 0.15
        }
    },
    "privacy": {
        "aggregate_only": True,
        "forbidden_fields": [
            "email","phone","mobile","whatsapp","full_name","first_name","last_name",
            "ip","ip_address","user_id","device_id","cookie","session_id","password",
            "pan","gstin","address","card_number"
        ],
        "forbidden_key_substrings": ["token","secret","authorization","credential"]
    }
}
CHANNELS = {
    "channels": [
        {"id":"linkedin","utm_source":"linkedin","utm_medium":"social","enabled":True},
        {"id":"x","utm_source":"x","utm_medium":"social","enabled":True},
        {"id":"email","utm_source":"cyberdudebivash","utm_medium":"email","enabled":False},
    ]
}
ECOSYSTEM = {
    "canonical_home": "https://www.cyberdudebivash.com/",
    "platforms": [
        {"id":"official-portal","url":"https://www.cyberdudebivash.com/"},
        {"id":"ai-security-hub","url":"https://cyberdudebivash.in/"},
    ]
}


def record(channel="linkedin", clicks=100, impressions=1000):
    return {
        "schema_version": 1,
        "campaign_id": "cdb-20260817-authority-all-12345678",
        "window_start": "2026-08-17",
        "window_end": "2026-08-18",
        "channel": channel,
        "platform": "official-portal",
        "metrics": {
            "impressions": impressions,
            "clicks": clicks,
            "engaged_visits": min(clicks, 70),
            "cta_actions": 10,
            "leads": 3,
            "conversions": 1,
        },
    }


class GrowthAttributionTests(unittest.TestCase):
    def test_campaign_id_is_deterministic(self):
        first = campaign_id("2026-08-17", "authority", "all")
        second = campaign_id("2026-08-17", "authority", "all")
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("cdb-20260817-authority-all-"))

    def test_tracking_preserves_existing_query_and_adds_utm(self):
        url = build_tracked_url(
            "https://cyberdudebivash.in/?view=enterprise",
            "cdb-20260817-authority-all-12345678",
            "LinkedIn",
            "Social",
            content="Executive Post",
        )
        self.assertIn("view=enterprise", url)
        self.assertIn("utm_source=linkedin", url)
        self.assertIn("utm_medium=social", url)
        self.assertIn("utm_content=executive-post", url)

    def test_campaign_bundle_only_uses_enabled_channels(self):
        bundle = create_campaign_bundle(
            ECOSYSTEM, CHANNELS, POLICY,
            campaign_date="2026-08-17",
            objective="demand",
            platform="ai-security-hub",
        )
        self.assertEqual(bundle["destination"], "https://cyberdudebivash.in/")
        self.assertIn("linkedin", bundle["tracking_urls"])
        self.assertNotIn("email", bundle["tracking_urls"])

    def test_destination_outside_ecosystem_is_rejected(self):
        with self.assertRaises(GrowthValidationError):
            create_campaign_bundle(
                ECOSYSTEM, CHANNELS, POLICY,
                campaign_date="2026-08-17",
                objective="demand",
                platform="ai-security-hub",
                destination="https://example.com/",
            )

    def test_lifecycle_transition_is_fail_closed(self):
        bundle = create_campaign_bundle(
            ECOSYSTEM, CHANNELS, POLICY,
            campaign_date="2026-08-17",
            objective="authority",
            platform="all",
        )
        approved = transition_campaign(bundle, "approved", POLICY)
        self.assertEqual(approved["state"], "approved")
        with self.assertRaises(GrowthValidationError):
            transition_campaign(bundle, "completed", POLICY)

    def test_performance_contract_rejects_personal_data_field(self):
        payload = record()
        payload["email"] = "person@example.com"
        with self.assertRaises(GrowthValidationError):
            validate_performance_record(payload, POLICY, CHANNELS)

    def test_disabled_channel_is_rejected(self):
        payload = record(channel="email")
        with self.assertRaises(GrowthValidationError):
            validate_performance_record(payload, POLICY, CHANNELS)

    def test_impossible_click_count_is_rejected(self):
        payload = record(clicks=1200, impressions=1000)
        with self.assertRaises(GrowthValidationError):
            validate_performance_record(payload, POLICY, CHANNELS)

    def test_scorecard_aggregates_and_bounds_index(self):
        one = record(channel="linkedin", clicks=100, impressions=1000)
        two = record(channel="x", clicks=50, impressions=1000)
        scorecard = aggregate_records([one, two], POLICY, CHANNELS)
        self.assertEqual(scorecard["metrics"]["impressions"], 2000)
        self.assertEqual(scorecard["metrics"]["clicks"], 150)
        self.assertGreaterEqual(scorecard["performance_index"], 0)
        self.assertLessEqual(scorecard["performance_index"], 100)
        self.assertEqual(set(scorecard["channels"]), {"linkedin", "x"})


if __name__ == "__main__":
    unittest.main()

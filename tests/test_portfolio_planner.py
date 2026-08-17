import datetime as dt
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import load_json
from portfolio_planner import PlanningError, normalize_history, build_campaign_plan


class PortfolioPlannerTests(unittest.TestCase):
    def setUp(self):
        self.ecosystem = load_json("config/ecosystem.json")
        self.policy = load_json("config/editorial-policy.json")
        self.as_of = dt.date(2026, 8, 17)

    def record(self, days_ago, platform, objective="authority", campaign_id=None):
        date_value = self.as_of - dt.timedelta(days=days_ago)
        return {
            "campaign_id": campaign_id or f"cdb-{platform}-{days_ago}",
            "campaign_date": date_value.isoformat(),
            "platform": platform,
            "objective": objective,
        }

    def test_zero_history_uses_strategic_priority_then_stable_id(self):
        plan = build_campaign_plan(self.ecosystem, self.policy, [], as_of=self.as_of)
        self.assertEqual("planned", plan["status"])
        self.assertEqual("official-portal", plan["platform"])
        self.assertEqual("authority", plan["objective"])

    def test_recent_platform_is_excluded_by_cooldown(self):
        history = [self.record(5, "official-portal")]
        plan = build_campaign_plan(self.ecosystem, self.policy, history, as_of=self.as_of)
        self.assertEqual("planned", plan["status"])
        self.assertNotEqual("official-portal", plan["platform"])
        excluded = {item["platform"]: item for item in plan["excluded_platforms"]}
        self.assertIn("official-portal", excluded)
        self.assertIn("cooldown", excluded["official-portal"]["reasons"][0])

    def test_underrepresented_platform_beats_more_frequent_platform(self):
        history = [
            self.record(70, "official-portal", "authority"),
            self.record(40, "official-portal", "demand"),
            self.record(20, "official-portal", "adoption"),
            self.record(65, "ai-security-hub", "authority"),
        ]
        plan = build_campaign_plan(self.ecosystem, self.policy, history, as_of=self.as_of)
        self.assertEqual("planned", plan["status"])
        self.assertNotEqual("official-portal", plan["platform"])

    def test_iso_week_capacity_exhaustion_is_clean_noop(self):
        history = [
            self.record(0, "academy", "education"),
            self.record(1, "trustx", "trust"),
        ]
        plan = build_campaign_plan(self.ecosystem, self.policy, history, as_of=self.as_of)
        self.assertEqual("capacity-exhausted", plan["status"])
        self.assertIsNone(plan["platform"])

    def test_rolling_capacity_blocks_across_iso_week_boundary(self):
        # Monday 2026-08-17; campaigns on previous Sunday/Saturday are in prior ISO week
        # but still inside the 7-day rolling window.
        history = [
            self.record(1, "academy", "education"),
            self.record(2, "trustx", "trust"),
        ]
        plan = build_campaign_plan(self.ecosystem, self.policy, history, as_of=self.as_of)
        self.assertEqual("capacity-exhausted", plan["status"])
        self.assertIn("rolling", plan["reasons"][0])

    def test_global_spacing_blocks_manual_or_automatic_run(self):
        history = [self.record(1, "academy", "education")]
        plan = build_campaign_plan(self.ecosystem, self.policy, history, as_of=self.as_of)
        self.assertEqual("capacity-exhausted", plan["status"])
        self.assertIn("spacing", plan["reasons"][0])

    def test_objective_rotation_avoids_overused_objective(self):
        history = [
            self.record(20, "academy", "authority"),
            self.record(12, "trustx", "authority"),
            self.record(8, "cti-platform", "demand"),
        ]
        # Force a platform that supports both authority and demand.
        plan = build_campaign_plan(
            self.ecosystem,
            self.policy,
            history,
            as_of=self.as_of,
            requested_platform="ai-security-hub",
        )
        self.assertEqual("planned", plan["status"])
        self.assertNotEqual("authority", plan["objective"])

    def test_manual_platform_request_still_respects_cooldown(self):
        history = [self.record(5, "trustx", "trust")]
        plan = build_campaign_plan(
            self.ecosystem,
            self.policy,
            history,
            as_of=self.as_of,
            requested_platform="trustx",
            requested_objective="authority",
        )
        self.assertEqual("blocked", plan["status"])
        self.assertIn("cooldown", plan["reasons"][0])

    def test_manual_all_platform_campaign_is_disabled(self):
        plan = build_campaign_plan(self.ecosystem, self.policy, [], as_of=self.as_of, requested_platform="all")
        self.assertEqual("blocked", plan["status"])

    def test_unknown_manual_platform_fails_closed(self):
        with self.assertRaises(PlanningError):
            build_campaign_plan(
                self.ecosystem, self.policy, [], as_of=self.as_of, requested_platform="unknown-platform"
            )

    def test_all_platform_history_touches_every_platform(self):
        history = [self.record(5, "all", "authority")]
        plan = build_campaign_plan(self.ecosystem, self.policy, history, as_of=self.as_of)
        self.assertEqual("no-eligible-platform", plan["status"])
        normalized, warnings = normalize_history(
            history,
            as_of=self.as_of,
            platform_ids={item["id"] for item in self.ecosystem["platforms"]},
            objective_ids={"authority", "demand", "adoption", "launch", "education", "trust"},
        )
        self.assertEqual("all", normalized[0]["platform"])
        self.assertEqual([], warnings)

    def test_reserved_prefix_with_malformed_title_fails_closed(self):
        bad = [{"title": "Global Campaign: malformed", "createdAt": "2026-08-10T00:00:00Z"}]
        with self.assertRaises(PlanningError):
            build_campaign_plan(self.ecosystem, self.policy, bad, as_of=self.as_of)

    def test_unrelated_issue_history_is_ignored(self):
        history = [{"title": "P0 Governance: unrelated", "createdAt": "2026-08-10T00:00:00Z"}]
        plan = build_campaign_plan(self.ecosystem, self.policy, history, as_of=self.as_of)
        self.assertEqual("planned", plan["status"])
        self.assertEqual(0, plan["history_records"])

    def test_same_inputs_produce_identical_plan(self):
        history = [
            self.record(30, "official-portal", "authority"),
            self.record(18, "ai-security-hub", "demand"),
        ]
        first = build_campaign_plan(self.ecosystem, self.policy, history, as_of=self.as_of)
        second = build_campaign_plan(self.ecosystem, self.policy, history, as_of=self.as_of)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

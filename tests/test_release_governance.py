import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from release_governance import GovernanceError, apply_ruleset, load_json, validate_contract, verify_live


class ReleaseGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_json(ROOT / "config" / "release-governance.json")
        self.ruleset = load_json(ROOT / "config" / "github-main-ruleset.json")

    def test_checked_in_contract_is_valid(self):
        validate_contract(self.policy, self.ruleset)

    def test_missing_required_check_fails_closed(self):
        broken = json.loads(json.dumps(self.ruleset))
        broken["rules"][3]["parameters"]["required_status_checks"].pop()
        with self.assertRaises(GovernanceError):
            validate_contract(self.policy, broken)

    def test_bypass_actor_fails_closed(self):
        broken = json.loads(json.dumps(self.ruleset))
        broken["bypass_actors"] = [{"actor_id": 1, "actor_type": "RepositoryRole", "bypass_mode": "always"}]
        with self.assertRaises(GovernanceError):
            validate_contract(self.policy, broken)

    def test_live_verification_requires_named_active_ruleset(self):
        with patch("release_governance.list_repository_rulesets", return_value=[]):
            with self.assertRaises(GovernanceError):
                verify_live(self.policy)
        with patch(
            "release_governance.list_repository_rulesets",
            return_value=[{"id": 7, "name": self.policy["ruleset_name"], "enforcement": "evaluate"}],
        ):
            with self.assertRaises(GovernanceError):
                verify_live(self.policy)

    def test_live_verification_accepts_active_ruleset(self):
        expected = {"id": 42, "name": self.policy["ruleset_name"], "enforcement": "active"}
        with patch("release_governance.list_repository_rulesets", return_value=[expected]):
            self.assertEqual(expected, verify_live(self.policy))

    def test_apply_creates_ruleset_when_absent(self):
        with patch("release_governance.list_repository_rulesets", return_value=[]), patch(
            "release_governance._request", return_value={"id": 11, "enforcement": "active"}
        ) as request:
            result = apply_ruleset(self.policy, self.ruleset, token="token")
        self.assertEqual(11, result["id"])
        self.assertEqual("POST", request.call_args.kwargs["method"])

    def test_apply_updates_existing_ruleset_idempotently(self):
        existing = [{"id": 99, "name": self.policy["ruleset_name"], "enforcement": "active"}]
        with patch("release_governance.list_repository_rulesets", return_value=existing), patch(
            "release_governance._request", return_value={"id": 99, "enforcement": "active"}
        ) as request:
            result = apply_ruleset(self.policy, self.ruleset, token="token")
        self.assertEqual(99, result["id"])
        self.assertEqual("PUT", request.call_args.kwargs["method"])
        self.assertTrue(request.call_args.args[0].endswith("/rulesets/99"))


if __name__ == "__main__":
    unittest.main()

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from claims_governance import (
    approved_public_claims,
    find_claim_violations,
    find_sensitive_identifiers,
    load_policy,
    validate_policy,
    validate_publication_text,
)


class ClaimsGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy()

    def test_policy_is_valid(self):
        self.assertEqual([], validate_policy(self.policy))

    def test_unverified_legal_and_compliance_claims_fail_closed(self):
        claims = {item["id"]: item for item in self.policy["claims"]}
        for claim_id in (
            "legal-entity-name",
            "gst-registration",
            "msme-udyam-registration",
            "startup-india-recognition",
        ):
            self.assertEqual("hold", claims[claim_id]["status"])
            self.assertFalse(claims[claim_id].get("approved_public_wording"))

    def test_payment_plan_identifiers_are_private_only(self):
        claims = {item["id"]: item for item in self.policy["claims"]}
        claim = claims["payment-plan-identifiers"]
        self.assertEqual("private-only", claim["status"])
        self.assertEqual("forbidden", claim["public_disclosure"])

    def test_market_leadership_claim_is_prohibited(self):
        claims = {item["id"]: item for item in self.policy["claims"]}
        self.assertEqual(
            "prohibited",
            claims["market-leadership-india-first-ai-native"]["status"],
        )

    def test_approved_location_wording_is_deterministic(self):
        approved = {item["id"]: item for item in approved_public_claims(self.policy)}
        self.assertEqual(
            "Odisha, India",
            approved["public-location-wording"]["approved_public_wording"],
        )

    def test_detects_unapproved_market_superlative(self):
        text = "CYBERDUDEBIVASH® is " + "India" + "'s " + "1st AI-Native Cybersecurity Platform"
        findings = find_claim_violations(text, self.policy)
        self.assertTrue(any(item.startswith("prohibited:") for item in findings))

    def test_detects_unapproved_legal_entity_wording(self):
        text = "CYBERDUDEBIVASH " + "PRIVATE " + "LIMITED provides security services."
        self.assertIn(
            "not-approved:legal-entity-name",
            find_claim_violations(text, self.policy),
        )

    def test_detects_sensitive_identifiers_without_storing_real_values(self):
        pan = "ABCDE" + "1234" + "F"
        gstin = "29" + "ABCDE" + "1234" + "F" + "1Z5"
        plan_id = "plan_" + "AbCdEf123456"
        self.assertIn("pan", find_sensitive_identifiers(pan, self.policy))
        self.assertIn("gstin", find_sensitive_identifiers(gstin, self.policy))
        self.assertIn("razorpay_plan_id", find_sensitive_identifiers(plan_id, self.policy))

    def test_publication_guard_accepts_normal_product_copy(self):
        validate_publication_text(
            "CYBERDUDEBIVASH® provides AI security, threat intelligence and practitioner tooling.",
            self.policy,
        )

    def test_approved_legal_claim_requires_authoritative_evidence(self):
        modified = copy.deepcopy(self.policy)
        claim = next(
            item for item in modified["claims"] if item["id"] == "legal-entity-name"
        )
        claim.update(
            {
                "status": "approved",
                "approved_public_wording": "Example approved legal wording",
                "evidence_type": "owner-confirmed-public-directory",
                "evidence_reference": "internal-review-record",
                "evidence_owner": "owner",
                "approved_on": "2026-08-17",
                "review_due_on": "2027-08-17",
            }
        )
        failures = validate_policy(modified)
        self.assertTrue(
            any("requires authoritative evidence_type" in item for item in failures)
        )


if __name__ == "__main__":
    unittest.main()

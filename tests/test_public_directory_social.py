import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common import load_json
from validate_public_directory import validate


class RetiredPublicSocialIdentityTests(unittest.TestCase):
    def test_first_party_directory_preserves_approved_channels_only(self):
        data = load_json("config/public-directory.json")
        social = data["channels"]
        self.assertTrue(any(x["id"] == "linkedin" for x in social))
        self.assertTrue(any(x["id"] == "instagram" for x in social))
        self.assertFalse(any(x["id"] == "facebook" for x in social))
        self.assertFalse(any("orcid.org" in x["url"] for x in social))

    def test_readding_unverified_external_identity_is_rejected(self):
        data = load_json("config/public-directory.json")
        for host in ("facebook.com", "orcid.org"):
            injected = copy.deepcopy(data)
            injected["channels"].append({"id": "synthetic-unverified", "name": "Unverified", "url": f"https://{host}/unverified"})
            with self.subTest(host=host), patch("validate_public_directory.load_json", return_value=injected):
                errors = validate()
                self.assertTrue(any("unverified external social identity" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

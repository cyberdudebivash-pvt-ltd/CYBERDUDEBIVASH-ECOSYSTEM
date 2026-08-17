import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import load_json
from generate_campaign import render, select_platforms


class CampaignTests(unittest.TestCase):
    def test_all_platforms_render_brand_and_cta(self):
        data = load_json("config/ecosystem.json")
        selected = select_platforms(data, "all")
        content = render(selected, "authority")
        self.assertIn("CYBERDUDEBIVASH®", content)
        self.assertIn("https://www.cyberdudebivash.com/", content)
        self.assertIn("Mandatory review gates", content)

    def test_single_platform_uses_platform_url(self):
        data = load_json("config/ecosystem.json")
        selected = select_platforms(data, "ai-security-hub")
        content = render(selected, "demand")
        self.assertIn("https://cyberdudebivash.in/", content)


if __name__ == "__main__":
    unittest.main()

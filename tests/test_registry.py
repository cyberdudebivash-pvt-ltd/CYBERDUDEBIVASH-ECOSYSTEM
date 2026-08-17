import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_registry import validate


class RegistryTests(unittest.TestCase):
    def test_registry_is_valid(self):
        self.assertEqual(validate(), [])


if __name__ == "__main__":
    unittest.main()

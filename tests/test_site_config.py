import json
import tempfile
import unittest
from pathlib import Path

from weather_analysis.config import load_sites


class SiteConfigTest(unittest.TestCase):
    def test_local_sites_override_bundled_examples(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sites.local.json"
            sites = [{"county": "Test region", "name": "Test site", "lon": 2.0, "lat": 3.0}]
            path.write_text(json.dumps(sites), encoding="utf-8")
            self.assertEqual(load_sites(path), sites)

    def test_invalid_coordinates_and_identity_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sites.local.json"
            for update in ({"lat": 91}, {"lon": float("nan")}, {"lon": True}, {"name": ""}):
                with self.subTest(update=update):
                    site = {"county": "Test", "name": "Test", "lon": 2, "lat": 3, **update}
                    path.write_text(json.dumps([site]), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_sites(path)

import tempfile
import unittest
from pathlib import Path

from weather_analysis.paths import resolve_data_dir


class RuntimePathsTest(unittest.TestCase):
    def test_explicit_data_directory_takes_precedence(self):
        with tempfile.TemporaryDirectory() as temporary:
            expected = Path(temporary) / "custom"

            actual = resolve_data_dir(
                {"WEATHER_ANALYSIS_DATA_DIR": str(expected)},
                os_name="nt",
                home=Path(temporary) / "home",
            )

            self.assertEqual(expected.resolve(), actual)

    def test_platform_defaults_are_user_writable_locations(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)

            windows = resolve_data_dir({}, os_name="nt", home=home)
            unix = resolve_data_dir({}, os_name="posix", home=home)

            self.assertEqual((home / "AppData" / "Local" / "weather-analysis").resolve(), windows)
            self.assertEqual((home / ".local" / "state" / "weather-analysis").resolve(), unix)


if __name__ == "__main__":
    unittest.main()

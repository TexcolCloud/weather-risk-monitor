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
                project_root=Path(temporary) / "project",
            )

            self.assertEqual(expected.resolve(), actual)

    def test_project_root_is_the_default_data_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_root = Path(temporary) / "project"

            actual = resolve_data_dir({}, project_root=project_root)

            self.assertEqual(project_root.resolve(), actual)


if __name__ == "__main__":
    unittest.main()

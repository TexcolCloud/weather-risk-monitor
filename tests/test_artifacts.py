import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from weather_analysis.artifacts import ArtifactStore


class ArtifactStoreTest(unittest.TestCase):
    def test_report_audit_and_pending_outbox_are_written(self):
        created_at = datetime(2026, 7, 14, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch("weather_analysis.artifacts.REPORTS_DIR", root / "reports"),
                patch("weather_analysis.artifacts.OUTBOX_DIR", root / "outbox"),
            ):
                store = ArtifactStore()
                audit_path = store.write_json("hourly", created_at, {"total": 1})
                report_path = store.write_report("hourly", created_at, "report\n")
                outbox_path = store.publish("hourly", report_path, created_at)
                no_risk_path = store.mark_not_required("hourly", report_path, created_at)

            self.assertEqual("0800.json", audit_path.name)
            self.assertEqual("0800.md", report_path.name)
            self.assertTrue(outbox_path.exists())
            self.assertEqual(outbox_path, no_risk_path)
            self.assertEqual("not_required", json.loads(outbox_path.read_text(encoding="utf-8"))["status"])

import json
import tempfile
import unittest
from datetime import datetime, timedelta
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
                audit_path = store.write_json("hourly", created_at, {"total": 1}, created_at)
                report_path = store.write_report("hourly", created_at, "report\n", created_at)
                outbox_path = store.publish("hourly", report_path, created_at, created_at)
                no_risk_path = store.mark_not_required(
                    "hourly", report_path, created_at, created_at + timedelta(seconds=1)
                )
                failed_path = store.mark_failed(
                    "hourly", report_path, created_at, created_at + timedelta(seconds=2)
                )

            self.assertTrue(audit_path.name.startswith("0800-080000"))
            self.assertTrue(report_path.name.startswith("0800-080000"))
            self.assertTrue(outbox_path.exists())
            self.assertNotEqual(outbox_path, no_risk_path)
            self.assertEqual(
                "pending", json.loads(outbox_path.read_text(encoding="utf-8"))["status"]
            )
            self.assertEqual(
                "not_required", json.loads(no_risk_path.read_text(encoding="utf-8"))["status"]
            )
            self.assertEqual(
                "failed", json.loads(failed_path.read_text(encoding="utf-8"))["status"]
            )

    def test_prune_removes_only_expired_date_directories(self):
        now = datetime(2026, 7, 15, tzinfo=ZoneInfo("Asia/Shanghai"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_report = root / "reports" / "hourly" / "2025-07-14"
            current_report = root / "reports" / "hourly" / "2026-07-15"
            old_outbox = root / "outbox" / "2025-07-14"
            for directory in (old_report, current_report, old_outbox):
                directory.mkdir(parents=True)
                (directory / "result.json").write_text("{}", encoding="utf-8")

            with (
                patch("weather_analysis.artifacts.REPORTS_DIR", root / "reports"),
                patch("weather_analysis.artifacts.OUTBOX_DIR", root / "outbox"),
            ):
                removed = ArtifactStore().prune(now, retention_days=365)

            self.assertEqual(2, removed)
            self.assertFalse(old_report.exists())
            self.assertFalse(old_outbox.exists())
            self.assertTrue(current_report.exists())

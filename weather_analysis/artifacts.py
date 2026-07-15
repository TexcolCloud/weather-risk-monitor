"""Local report storage and a transport-neutral pending-delivery outbox."""

import json
import os
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Protocol


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
OUTBOX_DIR = PROJECT_ROOT / "outbox"
ARTIFACT_RETENTION_DAYS = int(os.environ.get("WEATHER_ANALYSIS_ARTIFACT_RETENTION_DAYS", "365"))


class ReportPublisher(Protocol):
    def publish(
        self, kind: str, report_path: Path, target_at: datetime, created_at: datetime
    ) -> Path:
        """Register a generated report for a future delivery channel."""

    def mark_not_required(
        self, kind: str, report_path: Path, target_at: datetime, created_at: datetime
    ) -> Path:
        """Record that the latest report does not need delivery."""

    def mark_preview(
        self, kind: str, report_path: Path, target_at: datetime, created_at: datetime
    ) -> Path:
        """Record a startup preview that must not be externally delivered."""


class LocalOutboxPublisher:
    """Default publisher that only records a pending local delivery event."""

    @staticmethod
    def _path(kind: str, target_at: datetime, created_at: datetime) -> Path:
        date_dir = OUTBOX_DIR / target_at.strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        return (
            date_dir / f"{target_at.strftime('%H%M')}-{created_at.strftime('%H%M%S%f')}-{kind}.json"
        )

    def _record(
        self, kind: str, report_path: Path, target_at: datetime, created_at: datetime, status: str
    ) -> Path:
        path = self._path(kind, target_at, created_at)
        payload = {
            "kind": kind,
            "status": status,
            "targetAt": target_at.isoformat(),
            "createdAt": created_at.isoformat(),
            "reportPath": str(report_path),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def publish(
        self, kind: str, report_path: Path, target_at: datetime, created_at: datetime
    ) -> Path:
        return self._record(kind, report_path, target_at, created_at, "pending")

    def mark_not_required(
        self, kind: str, report_path: Path, target_at: datetime, created_at: datetime
    ) -> Path:
        return self._record(kind, report_path, target_at, created_at, "not_required")

    def mark_preview(
        self, kind: str, report_path: Path, target_at: datetime, created_at: datetime
    ) -> Path:
        return self._record(kind, report_path, target_at, created_at, "preview")


class ArtifactStore:
    def __init__(self, publisher: ReportPublisher | None = None):
        self.publisher = publisher or LocalOutboxPublisher()

    @staticmethod
    def _path(kind: str, target_at: datetime, created_at: datetime, suffix: str) -> Path:
        directory = REPORTS_DIR / kind / target_at.strftime("%Y-%m-%d")
        directory.mkdir(parents=True, exist_ok=True)
        return (
            directory / f"{target_at.strftime('%H%M')}-{created_at.strftime('%H%M%S%f')}.{suffix}"
        )

    def write_json(
        self, kind: str, target_at: datetime, result: dict, created_at: datetime | None = None
    ) -> Path:
        created_at = created_at or target_at
        path = self._path(kind, target_at, created_at, "json")
        payload = {
            "kind": kind,
            "targetAt": target_at.isoformat(),
            "generatedAt": created_at.isoformat(),
            "result": result,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def write_report(
        self, kind: str, target_at: datetime, report: str, created_at: datetime | None = None
    ) -> Path:
        created_at = created_at or target_at
        path = self._path(kind, target_at, created_at, "md")
        path.write_text(report, encoding="utf-8")
        return path

    def publish(
        self, kind: str, report_path: Path, target_at: datetime, created_at: datetime
    ) -> Path:
        return self.publisher.publish(kind, report_path, target_at, created_at)

    def mark_not_required(
        self, kind: str, report_path: Path, target_at: datetime, created_at: datetime
    ) -> Path:
        return self.publisher.mark_not_required(kind, report_path, target_at, created_at)

    def mark_preview(
        self, kind: str, report_path: Path, target_at: datetime, created_at: datetime
    ) -> Path:
        return self.publisher.mark_preview(kind, report_path, target_at, created_at)

    @staticmethod
    def _prune_root(root: Path, cutoff: date) -> int:
        removed = 0
        if not root.exists():
            return removed
        for directory in root.rglob("*"):
            if not directory.is_dir():
                continue
            try:
                directory_date = date.fromisoformat(directory.name)
            except ValueError:
                continue
            if directory_date < cutoff:
                shutil.rmtree(directory)
                removed += 1
        return removed

    def prune(self, now: datetime, retention_days: int = ARTIFACT_RETENTION_DAYS) -> int:
        if retention_days < 1:
            return 0
        cutoff = (now - timedelta(days=retention_days)).date()
        return self._prune_root(REPORTS_DIR, cutoff) + self._prune_root(OUTBOX_DIR, cutoff)

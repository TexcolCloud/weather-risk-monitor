"""Local report storage and a transport-neutral pending-delivery outbox."""

import json
from datetime import datetime
from pathlib import Path
from typing import Protocol


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
OUTBOX_DIR = PROJECT_ROOT / "outbox"


class ReportPublisher(Protocol):
    def publish(self, kind: str, report_path: Path, created_at: datetime) -> Path:
        """Register a generated report for a future delivery channel."""

    def mark_not_required(self, kind: str, report_path: Path, created_at: datetime) -> Path:
        """Record that the latest report does not need delivery."""


class LocalOutboxPublisher:
    """Default publisher that only records a pending local delivery event."""

    @staticmethod
    def _path(kind: str, created_at: datetime) -> Path:
        date_dir = OUTBOX_DIR / created_at.strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        return date_dir / f"{created_at.strftime('%H%M')}-{kind}.json"

    def _record(self, kind: str, report_path: Path, created_at: datetime, status: str) -> Path:
        path = self._path(kind, created_at)
        payload = {
            "kind": kind,
            "status": status,
            "createdAt": created_at.isoformat(),
            "reportPath": str(report_path),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def publish(self, kind: str, report_path: Path, created_at: datetime) -> Path:
        return self._record(kind, report_path, created_at, "pending")

    def mark_not_required(self, kind: str, report_path: Path, created_at: datetime) -> Path:
        return self._record(kind, report_path, created_at, "not_required")


class ArtifactStore:
    def __init__(self, publisher: ReportPublisher | None = None):
        self.publisher = publisher or LocalOutboxPublisher()

    @staticmethod
    def _path(kind: str, created_at: datetime, suffix: str) -> Path:
        directory = REPORTS_DIR / kind / created_at.strftime("%Y-%m-%d")
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{created_at.strftime('%H%M')}.{suffix}"

    def write_json(self, kind: str, created_at: datetime, result: dict) -> Path:
        path = self._path(kind, created_at, "json")
        payload = {
            "kind": kind,
            "generatedAt": created_at.isoformat(),
            "result": result,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def write_report(self, kind: str, created_at: datetime, report: str) -> Path:
        path = self._path(kind, created_at, "md")
        path.write_text(report, encoding="utf-8")
        return path

    def publish(self, kind: str, report_path: Path, created_at: datetime) -> Path:
        return self.publisher.publish(kind, report_path, created_at)

    def mark_not_required(self, kind: str, report_path: Path, created_at: datetime) -> Path:
        return self.publisher.mark_not_required(kind, report_path, created_at)

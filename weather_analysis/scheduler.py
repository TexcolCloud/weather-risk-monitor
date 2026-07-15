"""Long-running scheduled weather analysis jobs."""

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .artifacts import ArtifactStore
from .hourly_report import HourlyReportGenerator
from .models import Room
from .report import ReportGenerator
from .weather import WeatherService


TIMEZONE = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger(__name__)


class ScheduledJobRunner:
    def __init__(self, rooms: list[Room], region: str = "示例区域", artifacts: ArtifactStore | None = None):
        self.rooms = rooms
        self.region = region
        self.artifacts = artifacts or ArtifactStore()
        self._lock = asyncio.Lock()
        self._last_hourly_target: str | None = None

    async def _run_exclusive(self, kind: str, callback):
        if self._lock.locked():
            logger.warning("任务跳过：已有任务运行中 kind=%s", kind)
            return None
        async with self._lock:
            started = datetime.now(TIMEZONE)
            logger.info("任务开始 kind=%s scheduled_at=%s", kind, started.isoformat())
            try:
                return await callback(started)
            except Exception:
                logger.exception("任务失败 kind=%s", kind)
                return None
            finally:
                elapsed = (datetime.now(TIMEZONE) - started).total_seconds()
                logger.info("任务结束 kind=%s duration_seconds=%.2f", kind, elapsed)

    async def run_full_forecast(self):
        async def callback(started: datetime):
            result = await WeatherService.run(self.rooms)
            report = ReportGenerator(self.rooms, region=self.region).generate(result)
            json_path = self.artifacts.write_json("full", started, result)
            report_path = self.artifacts.write_report("full", started, report)
            outbox_path = self.artifacts.publish("full", report_path, started)
            logger.info(
                "完整预测完成 total=%s warned=%s failed=%s partial_failed=%s report=%s audit=%s outbox=%s",
                result.get("total", 0),
                result.get("warned", 0),
                result.get("failed", 0),
                result.get("partialFailed", 0),
                report_path,
                json_path,
                outbox_path,
            )
            return result, report

        return await self._run_exclusive("full", callback)

    async def run_hourly_risk(self, target_start: datetime | None = None):
        target_start = target_start or datetime.now(TIMEZONE).replace(minute=0, second=0, microsecond=0)
        if target_start.tzinfo is None:
            target_start = target_start.replace(tzinfo=TIMEZONE)
        else:
            target_start = target_start.astimezone(TIMEZONE)
        target_start = target_start.replace(minute=0, second=0, microsecond=0)
        target_id = target_start.isoformat()
        if self._last_hourly_target == target_id:
            logger.info("任务跳过：目标整点已完成 target=%s", target_id)
            return None

        async def callback(started: datetime):
            result = await WeatherService.run_hourly_risk(self.rooms, target_start)
            artifact_time = datetime.fromisoformat(result["targetStart"])
            json_path = self.artifacts.write_json("hourly", artifact_time, result)
            high_risk_count = len(result["immediateRisks"]) + len(result["outlookRisks"])
            report = HourlyReportGenerator(self.region).generate(result)
            report_path = self.artifacts.write_report("hourly", artifact_time, report)
            if high_risk_count:
                outbox_path = self.artifacts.publish("hourly", report_path, artifact_time)
            else:
                outbox_path = self.artifacts.mark_not_required("hourly", report_path, artifact_time)
            self._last_hourly_target = result["targetStart"]
            logger.info(
                "整点风险完成 target=%s total=%s immediate=%s outlook=%s failed=%s partial_failed=%s "
                "warning_failed=%s audit=%s report=%s outbox=%s",
                result["targetStart"],
                result["total"],
                len(result["immediateRisks"]),
                len(result["outlookRisks"]),
                result["failed"],
                result["partialFailed"],
                result["warningFailed"],
                json_path,
                report_path or "-",
                outbox_path or "-",
            )
            return result, report_path

        return await self._run_exclusive("hourly", callback)


def create_scheduler(runner: ScheduledJobRunner) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    common = {
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 300,
        "replace_existing": True,
    }
    scheduler.add_job(
        runner.run_hourly_risk,
        CronTrigger(minute=0, timezone=TIMEZONE),
        id="hourly-risk",
        **common,
    )
    scheduler.add_job(
        runner.run_full_forecast,
        CronTrigger(hour="8,20", minute=10, timezone=TIMEZONE),
        id="full-forecast",
        **common,
    )
    return scheduler


def next_complete_hour(now: datetime | None = None) -> datetime:
    now = now or datetime.now(TIMEZONE)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TIMEZONE)
    else:
        now = now.astimezone(TIMEZONE)
    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


async def run_daemon(runner: ScheduledJobRunner, immediate: bool = True) -> None:
    scheduler = create_scheduler(runner)
    scheduler.start()
    logger.info("天气分析守护进程已启动")
    try:
        if immediate:
            target = next_complete_hour()
            logger.info("启动即时检查 target=%s", target.isoformat())
            await runner.run_hourly_risk(target)
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)
        logger.info("天气分析守护进程已停止")

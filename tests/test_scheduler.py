import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

from weather_analysis.scheduler import ScheduledJobRunner, create_scheduler, next_complete_hour


TIMEZONE = ZoneInfo("Asia/Shanghai")


class SchedulerTest(unittest.TestCase):
    def test_scheduler_registers_hourly_and_twice_daily_jobs(self):
        scheduler = create_scheduler(ScheduledJobRunner([]))

        hourly = scheduler.get_job("hourly-risk")
        full = scheduler.get_job("full-forecast")

        self.assertIsNotNone(hourly)
        self.assertIsNotNone(full)
        self.assertEqual(1, hourly.max_instances)
        self.assertEqual(1, full.max_instances)
        self.assertIn("minute='0'", str(hourly.trigger))
        self.assertIn("hour='8,20'", str(full.trigger))
        self.assertIn("minute='10'", str(full.trigger))

    def test_next_complete_hour_rounds_up(self):
        now = datetime(2026, 7, 14, 8, 25, tzinfo=TIMEZONE)

        self.assertEqual(datetime(2026, 7, 14, 9, tzinfo=TIMEZONE), next_complete_hour(now))


class ScheduledJobRunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_same_target_hour_is_not_published_twice(self):
        target = datetime(2026, 7, 14, 8, tzinfo=TIMEZONE)
        result = {
            "targetStart": target.isoformat(),
            "immediateEnd": "2026-07-14T09:00:00+08:00",
            "outlookEnd": "2026-07-14T11:00:00+08:00",
            "total": 1,
            "failed": 0,
            "partialFailed": 0,
            "warningFailed": 0,
            "immediateRisks": [],
            "outlookRisks": [],
        }
        artifacts = Mock()
        artifacts.write_json.return_value = Path("audit.json")
        runner = ScheduledJobRunner([], artifacts=artifacts)

        with patch(
            "weather_analysis.scheduler.WeatherService.run_hourly_risk",
            new=AsyncMock(return_value=result),
        ) as fetch:
            await runner.run_hourly_risk(target)
            await runner.run_hourly_risk(target)

        self.assertEqual(1, fetch.await_count)
        self.assertEqual(1, artifacts.write_json.call_count)

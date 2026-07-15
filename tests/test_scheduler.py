import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, call, patch
from zoneinfo import ZoneInfo

from weather_analysis.runtime_state import RunStateStore
from weather_analysis.scheduler import (
    ScheduledJobRunner,
    create_scheduler,
    next_complete_hour,
    should_run_immediate_hourly,
)


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
        self.assertEqual("run_scheduled_hourly_risk", hourly.func.__name__)
        self.assertIn("minute='0'", str(hourly.trigger))
        self.assertIn("hour='8,20'", str(full.trigger))
        self.assertIn("minute='30'", str(full.trigger))

    def test_next_complete_hour_rounds_up(self):
        now = datetime(2026, 7, 14, 8, 25, tzinfo=TIMEZONE)

        self.assertEqual(datetime(2026, 7, 14, 9, tzinfo=TIMEZONE), next_complete_hour(now))

    def test_immediate_hourly_is_skipped_close_to_the_hour(self):
        self.assertFalse(
            should_run_immediate_hourly(datetime(2026, 7, 14, 18, 59, 59, tzinfo=TIMEZONE))
        )
        self.assertFalse(
            should_run_immediate_hourly(datetime(2026, 7, 14, 18, 59, tzinfo=TIMEZONE))
        )
        self.assertTrue(
            should_run_immediate_hourly(datetime(2026, 7, 14, 18, 58, 59, tzinfo=TIMEZONE))
        )


class ScheduledJobRunnerTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _hourly_result(target: datetime, failed: int = 0):
        return {
            "targetStart": target.isoformat(),
            "immediateEnd": (target + timedelta(hours=1)).isoformat(),
            "outlookEnd": (target + timedelta(hours=3)).isoformat(),
            "total": 1,
            "failed": failed,
            "partialFailed": 0,
            "warningFailed": 0,
            "immediateRisks": [],
            "outlookRisks": [],
        }

    async def test_default_hourly_target_is_next_complete_hour(self):
        target = datetime(2026, 7, 14, 17, tzinfo=TIMEZONE)
        artifacts = Mock()
        artifacts.write_json.return_value = Path("audit.json")
        artifacts.write_report.return_value = Path("report.md")
        artifacts.prune.return_value = 0
        runner = ScheduledJobRunner([], artifacts=artifacts)

        with (
            patch("weather_analysis.scheduler.next_complete_hour", return_value=target),
            patch(
                "weather_analysis.scheduler.WeatherService.run_hourly_risk",
                new=AsyncMock(return_value=self._hourly_result(target)),
            ) as fetch,
        ):
            await runner.run_hourly_risk()

        fetch.assert_awaited_once_with([], target, force_refresh=True)

    async def test_all_failed_hourly_run_is_marked_failed(self):
        target = datetime(2026, 7, 14, 17, tzinfo=TIMEZONE)
        artifacts = Mock()
        artifacts.write_json.return_value = Path("audit.json")
        artifacts.write_report.return_value = Path("report.md")
        artifacts.prune.return_value = 0
        runner = ScheduledJobRunner([], artifacts=artifacts)

        with patch(
            "weather_analysis.scheduler.WeatherService.run_hourly_risk",
            new=AsyncMock(return_value=self._hourly_result(target, failed=1)),
        ):
            await runner.run_hourly_risk(target)

        artifacts.mark_failed.assert_called_once_with(
            "hourly", Path("report.md"), target, artifacts.write_json.call_args.args[3]
        )
        artifacts.mark_not_required.assert_not_called()

    async def test_scheduled_hourly_waits_for_preview_instead_of_being_dropped(self):
        preview_target = datetime(2026, 7, 14, 19, tzinfo=TIMEZONE)
        scheduled_target = datetime(2026, 7, 14, 20, tzinfo=TIMEZONE)
        preview_started = asyncio.Event()
        release_preview = asyncio.Event()

        async def fetch(_rooms, target, force_refresh=False):
            if target == preview_target:
                preview_started.set()
                await release_preview.wait()
            return self._hourly_result(target)

        artifacts = Mock()
        artifacts.write_json.return_value = Path("audit.json")
        artifacts.write_report.return_value = Path("report.md")
        artifacts.prune.return_value = 0
        runner = ScheduledJobRunner([], artifacts=artifacts)

        with (
            patch("weather_analysis.scheduler.next_complete_hour", return_value=scheduled_target),
            patch(
                "weather_analysis.scheduler.WeatherService.run_hourly_risk",
                new=AsyncMock(side_effect=fetch),
            ) as weather_fetch,
        ):
            preview = asyncio.create_task(runner.run_hourly_risk(preview_target, publish=False))
            await preview_started.wait()
            scheduled = asyncio.create_task(runner.run_scheduled_hourly_risk())
            await asyncio.sleep(0)
            self.assertFalse(scheduled.done())

            release_preview.set()
            await asyncio.gather(preview, scheduled)

        self.assertEqual(
            [
                call([], preview_target, force_refresh=False),
                call([], scheduled_target, force_refresh=True),
            ],
            weather_fetch.await_args_list,
        )

    async def test_preview_does_not_skip_the_scheduled_hour_refresh(self):
        target = datetime(2026, 7, 14, 8, tzinfo=TIMEZONE)
        result = {
            "targetStart": target.isoformat(),
            "immediateEnd": "2026-07-14T09:00:00+08:00",
            "outlookEnd": "2026-07-14T11:00:00+08:00",
            "total": 1,
            "failed": 0,
            "partialFailed": 0,
            "warningFailed": 0,
            "immediateRisks": [{"name": "A", "county": "C", "stats": {}}],
            "outlookRisks": [],
        }
        artifacts = Mock()
        artifacts.write_json.return_value = Path("audit.json")
        artifacts.write_report.return_value = Path("report.md")
        artifacts.prune.return_value = 0
        runner = ScheduledJobRunner([], artifacts=artifacts)

        with patch(
            "weather_analysis.scheduler.WeatherService.run_hourly_risk",
            new=AsyncMock(return_value=result),
        ) as fetch:
            await runner.run_hourly_risk(target, publish=False)
            await runner.run_hourly_risk(target, publish=True)

        self.assertEqual(2, fetch.await_count)
        self.assertEqual(
            [
                call([], target, force_refresh=False),
                call([], target, force_refresh=True),
            ],
            fetch.await_args_list,
        )
        self.assertEqual(2, artifacts.write_json.call_count)
        artifacts.mark_preview.assert_called_once()
        artifacts.mark_not_required.assert_not_called()
        artifacts.publish.assert_called_once()

    async def test_missed_full_forecast_runs_once_per_scheduled_target(self):
        target = datetime(2026, 7, 14, 8, 10, tzinfo=TIMEZONE)
        with tempfile.TemporaryDirectory() as temporary:
            state_store = RunStateStore(Path(temporary) / "state.json")
            runner = ScheduledJobRunner([], artifacts=Mock(), state_store=state_store)
            result = {"total": 1, "failed": 0}
            with patch.object(
                runner,
                "run_full_forecast",
                new=AsyncMock(return_value=(result, "report")),
            ) as full_run:
                await runner.run_missed_full_forecast(datetime(2026, 7, 14, 8, 15, tzinfo=TIMEZONE))
                await runner.run_missed_full_forecast(datetime(2026, 7, 14, 8, 16, tzinfo=TIMEZONE))

            full_run.assert_awaited_once_with(target)
            self.assertTrue(state_store.is_completed("full", target))
